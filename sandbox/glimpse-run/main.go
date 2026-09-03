// glimpse-run is the tiny supervisor the Docker runner execs inside a sandbox.
//
//	glimpse-run -t <seconds> [-i <stdin-file>] -- cmd [args...]
//
// It starts the command in its own process group with stdin redirected from a
// file (or /dev/null), kills the whole group when the deadline passes (exit 124),
// and — crucially — kills the group again as soon as the main process exits, so
// background children the program left behind cannot keep the exec's stdout/stderr
// pipes open. Otherwise it exits with the command's own status (128+signal if it
// was killed, e.g. 137 for the OOM killer).
package main

import (
	"errors"
	"flag"
	"fmt"
	"os"
	"os/exec"
	"sync/atomic"
	"syscall"
	"time"
)

const (
	exitTimeout  = 124
	exitNotFound = 127
	exitUsage    = 2
)

func main() {
	timeout := flag.Float64("t", 0, "seconds before the process group is killed (0 = no limit)")
	stdinPath := flag.String("i", "", "file to use as stdin (default: /dev/null)")
	flag.Parse()
	args := flag.Args()
	if len(args) == 0 {
		fmt.Fprintln(os.Stderr, "usage: glimpse-run [-t seconds] [-i file] -- cmd [args...]")
		os.Exit(exitUsage)
	}

	in := os.Stdin
	path := *stdinPath
	if path == "" {
		path = os.DevNull
	}
	f, err := os.Open(path)
	if err != nil {
		fmt.Fprintf(os.Stderr, "glimpse-run: %v\n", err)
		os.Exit(exitUsage)
	}
	in = f

	cmd := exec.Command(args[0], args[1:]...)
	cmd.Stdin = in
	// *os.File targets are passed straight through as fds; Go creates no copying
	// goroutines, so Wait() returns when the child exits, not when the pipes close.
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.SysProcAttr = &syscall.SysProcAttr{Setpgid: true}

	if err := cmd.Start(); err != nil {
		fmt.Fprintf(os.Stderr, "glimpse-run: %v\n", err)
		os.Exit(exitNotFound)
	}
	pgid := cmd.Process.Pid

	var timedOut atomic.Bool
	if *timeout > 0 {
		d := time.Duration(*timeout * float64(time.Second))
		timer := time.AfterFunc(d, func() {
			timedOut.Store(true)
			_ = syscall.Kill(-pgid, syscall.SIGKILL)
		})
		defer timer.Stop()
	}

	waitErr := cmd.Wait()
	// Whatever happened, take the rest of the group with us.
	_ = syscall.Kill(-pgid, syscall.SIGKILL)

	if timedOut.Load() {
		os.Exit(exitTimeout)
	}
	os.Exit(exitStatus(waitErr))
}

func exitStatus(err error) int {
	if err == nil {
		return 0
	}
	var exitErr *exec.ExitError
	if errors.As(err, &exitErr) {
		if ws, ok := exitErr.Sys().(syscall.WaitStatus); ok {
			if ws.Signaled() {
				return 128 + int(ws.Signal())
			}
			return ws.ExitStatus()
		}
	}
	fmt.Fprintf(os.Stderr, "glimpse-run: %v\n", err)
	return exitNotFound
}

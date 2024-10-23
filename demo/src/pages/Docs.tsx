import { useEffect, useState } from "react";
import { Code2, Server, Lock, Cpu, Box } from "lucide-react";
import { Card } from "@/components/ui/card";
import CodeMirror from "@uiw/react-codemirror";
import { javascript } from "@codemirror/lang-javascript";

const APIReferenceSection = () => {
  const sampleAPICall = `fetch('https://glimpse-7eir.onrender.com/run-code-lambda', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    language: 'py',
    code: 'print("Hello from Glimpse!")',
    input: ''
  })
})
.then(response => response.json())
.then(data => console.log(data));`;

  const sampleResponse = `{
  "statusCode": 200,
  "body": {
    "output": "Hello from Glimpse!",
    "error": null,
    "executionTime": "0.245s"
  }
}`;

  const errorResponse = `{
  "statusCode": 400,
  "body": {
    "output": null,
    "error": "Language not supported. Available options: py, js",
    "executionTime": null
  }
}`;

  return (
    <section id="api" className="scroll-mt-16 space-y-6">
      <h2 className="text-3xl font-bold text-left">API Reference</h2>

      <Card className="p-6 space-y-8">
        <div>
          <h3 className="text-xl font-semibold mb-4 text-left">
            Execute Code Endpoint
          </h3>
          <div className="space-y-2">
            <p className="text-gray-600">
              Execute code snippets in supported programming languages.
            </p>
            <code className="block bg-gray-100 p-2 rounded text-left">
              POST /run-code-lambda
            </code>
          </div>
        </div>

        <div className="space-y-4">
          <h4 className="text-lg font-medium text-left">Request Parameters</h4>
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Parameter
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Type
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Required
                  </th>
                  <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                    Description
                  </th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    language
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    string
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    Yes
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    Programming language identifier ('py' or 'js')
                  </td>
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    code
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    string
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    Yes
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    Source code to execute (max 1MB)
                  </td>
                </tr>
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                    input
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    string
                  </td>
                  <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                    No
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">
                    Standard input for the program (optional)
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-4">
          <h4 className="text-lg font-medium text-left">Example Request</h4>
          <CodeMirror
            value={sampleAPICall}
            height="200px"
            extensions={[javascript()]}
            theme="dark"
            className="rounded-lg overflow-hidden"
          />
        </div>

        <div className="space-y-4">
          <h4 className="text-lg font-medium text-left">
            Success Response (200 OK)
          </h4>
          <CodeMirror
            value={sampleResponse}
            height="150px"
            extensions={[javascript()]}
            theme="dark"
            className="rounded-lg overflow-hidden"
          />
          <div className="space-y-2">
            <p className="font-medium text-left">Response Fields:</p>
            <ul className="list-disc pl-5 space-y-2 text-gray-600">
              <li>
                <code>output</code>: Program output (stdout)
              </li>
              <li>
                <code>error</code>: Error message if execution failed, null
                otherwise
              </li>
              <li>
                <code>executionTime</code>: Time taken to execute the code
              </li>
            </ul>
          </div>
        </div>

        <div className="space-y-4">
          <h4 className="text-lg font-medium text-left">
            Error Response (400 Bad Request)
          </h4>
          <CodeMirror
            value={errorResponse}
            height="150px"
            extensions={[javascript()]}
            theme="dark"
            className="rounded-lg overflow-hidden"
          />
        </div>

        <div className="space-y-4">
          <h4 className="text-lg font-medium text-left">Rate Limiting</h4>
          <div className="prose max-w-none">
            <ul className="list-disc pl-5 space-y-2 text-gray-600">
              <li>Maximum 1000 requests per hour per IP address</li>
              <li>Maximum execution time of 30 seconds per request</li>
              <li>Maximum code size of 1MB</li>
              <li>
                Rate limit headers are included in responses:
                <ul className="list-disc pl-5 mt-2">
                  <li>
                    <code>X-RateLimit-Limit</code>: Request limit per hour
                  </li>
                  <li>
                    <code>X-RateLimit-Remaining</code>: Remaining requests for
                    the current hour
                  </li>
                  <li>
                    <code>X-RateLimit-Reset</code>: Time when the rate limit
                    will reset (Unix timestamp)
                  </li>
                </ul>
              </li>
            </ul>
          </div>
        </div>
      </Card>
    </section>
  );
};

const DocsPage = () => {
  const [activeSection, setActiveSection] = useState("overview");

  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            setActiveSection(entry.target.id);
          }
        });
      },
      {
        rootMargin: "-20% 0% -80% 0%",
        threshold: 0,
      },
    );

    document.querySelectorAll("section[id]").forEach((section) => {
      observer.observe(section);
    });

    return () => observer.disconnect();
  }, []);

  const sections = [
    { id: "overview", title: "Overview", icon: Code2 },
    { id: "tech-stack", title: "Tech Stack", icon: Server },
    { id: "languages", title: "Supported Languages", icon: Box },
    { id: "api", title: "API Reference", icon: Cpu },
    { id: "terms", title: "Terms of Service", icon: Lock },
  ];

  const scrollToSection = (id: string) => {
    document.getElementById(id)?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6">
        <div className="lg:grid lg:grid-cols-4 lg:gap-8">
          {/* Side Navigation */}
          <div className="hidden lg:block">
            <div className="sticky top-24">
              <nav className="space-y-1">
                {sections.map(({ id, title, icon: Icon }) => (
                  <button
                    key={id}
                    onClick={() => scrollToSection(id)}
                    className={`w-full flex items-center space-x-2 px-4 py-2 text-sm rounded-lg transition-colors text-left ${
                      activeSection === id
                        ? "bg-gray-100 text-gray-900"
                        : "text-gray-100 bg-gray-500 hover:bg-gray-50 hover:text-gray-900"
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    <span>{title}</span>
                  </button>
                ))}
              </nav>
            </div>
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3 text-left">
            <div className="space-y-16">
              <section id="overview" className="scroll-mt-16 space-y-6">
                <h1 className="text-3xl font-bold text-left">
                  Glimpse Code Execution Service
                </h1>
                <p className="text-lg text-gray-600 text-left">
                  Glimpse is a powerful, secure API service that enables you to
                  execute code snippets directly from your client applications.
                  Built with security and scalability in mind, it provides a
                  seamless way to run code in various programming languages.
                </p>
                <Card className="p-6">
                  <h2 className="text-xl font-semibold mb-4 text-left">
                    Key Features
                  </h2>
                  <ul className="space-y-2">
                    <li className="flex items-center space-x-2">
                      <Lock className="h-5 w-5 text-green-500 flex-shrink-0" />
                      <span>Secure containerized execution environment</span>
                    </li>
                    <li className="flex items-center space-x-2">
                      <Cpu className="h-5 w-5 text-blue-500 flex-shrink-0" />
                      <span>Serverless architecture for optimal scaling</span>
                    </li>
                    <li className="flex items-center space-x-2">
                      <Box className="h-5 w-5 text-purple-500 flex-shrink-0" />
                      <span>Multiple programming language support</span>
                    </li>
                  </ul>
                </Card>
              </section>

              <section id="tech-stack" className="scroll-mt-16 space-y-6">
                <h2 className="text-3xl font-bold text-left">Tech Stack</h2>
                <Card className="p-6">
                  <h3 className="text-xl font-semibold mb-4 text-left">
                    Backend Architecture
                  </h3>
                  <ul className="space-y-4">
                    <li className="space-y-2">
                      <div className="font-medium text-left">
                        FastAPI on Render.com
                      </div>
                      <p className="text-gray-600 text-left">
                        High-performance web server handling API requests and
                        AWS Lambda communication
                      </p>
                    </li>
                    <li className="space-y-2">
                      <div className="font-medium text-left">AWS Lambda</div>
                      <p className="text-gray-600 text-left">
                        Secure code execution in isolated containers
                      </p>
                    </li>
                    <li className="space-y-2">
                      <div className="font-medium text-left">
                        Custom Runtime Image
                      </div>
                      <p className="text-gray-600 text-left">
                        Docker-based environment with extended language support
                      </p>
                    </li>
                  </ul>
                </Card>
              </section>

              <section id="languages" className="scroll-mt-16 space-y-6">
                <h2 className="text-3xl font-bold text-left">
                  Supported Languages
                </h2>
                <Card className="p-6">
                  <h3 className="text-xl font-semibold mb-4 text-left">
                    Currently Supported
                  </h3>
                  <ul className="space-y-4">
                    <li className="flex items-center space-x-4">
                      <div className="w-12 h-12 flex items-center justify-center bg-blue-100 rounded-lg flex-shrink-0">
                        <img
                          src="https://upload.wikimedia.org/wikipedia/commons/c/c3/Python-logo-notext.svg"
                          alt="Python"
                          className="w-8 h-8"
                        />
                      </div>
                      <div>
                        <h4 className="font-medium text-left">Python</h4>
                        <p className="text-sm text-gray-600 text-left">
                          Python 3.9 with common data science packages
                        </p>
                      </div>
                    </li>
                    <li className="flex items-center space-x-4">
                      <div className="w-12 h-12 flex items-center justify-center bg-yellow-100 rounded-lg flex-shrink-0">
                        <img
                          src="https://www.svgrepo.com/show/303206/javascript-logo.svg"
                          alt="JavaScript"
                          className="w-8 h-8"
                        />
                      </div>
                      <div>
                        <h4 className="font-medium text-left">JavaScript</h4>
                        <p className="text-sm text-gray-600 text-left">
                          Node.js 18.x runtime environment
                        </p>
                      </div>
                    </li>
                  </ul>
                </Card>
              </section>

              <APIReferenceSection />

              <section id="terms" className="scroll-mt-16 space-y-6">
                <h2 className="text-3xl font-bold text-left">
                  Terms of Service
                </h2>
                <Card className="p-6">
                  <div className="prose max-w-none">
                    <b>Free Use Policy</b>
                    <p>
                      Glimpse is provided as a free service for developers to
                      build innovative applications. We encourage you to use our
                      API to create educational tools, coding platforms, and
                      other creative solutions.
                    </p>
                    <br />
                    <b>Usage Guidelines</b>
                    <ul className="list-disc pl-8">
                      <li>
                        The service is provided "as is" without warranty of any
                        kind
                      </li>
                      <li>Fair usage limits apply to prevent abuse</li>
                      <li>
                        You may use the service for both personal and commercial
                        projects
                      </li>
                      <li>
                        You are responsible for any code executed through the
                        service
                      </li>
                    </ul>
                    <br />
                    <b>Rate Limits</b>
                    <p>
                      To ensure fair usage for all users, we implement the
                      following rate limits:
                    </p>
                    <ul className="list-disc pl-8">
                      <li>1000 requests per hour per IP address</li>
                      <li>Maximum execution time of 30 seconds per request</li>
                    </ul>
                  </div>
                </Card>
              </section>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default DocsPage;

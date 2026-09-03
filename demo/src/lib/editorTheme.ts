import { EditorView } from "@codemirror/view";
import { HighlightStyle, syntaxHighlighting } from "@codemirror/language";
import { tags as t } from "@lezer/highlight";

const chrome = EditorView.theme(
  {
    "&": {
      backgroundColor: "#0F2A2E",
      color: "#E6EEEC",
      fontSize: "13.5px",
      height: "100%",
    },
    ".cm-scroller": {
      fontFamily: '"IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, monospace',
      lineHeight: "1.6",
      overflow: "auto",
    },
    ".cm-content": { padding: "14px 0", caretColor: "#F2B84B" },
    ".cm-line": { padding: "0 16px" },
    "&.cm-focused .cm-cursor": { borderLeftColor: "#F2B84B", borderLeftWidth: "2px" },
    "&.cm-focused .cm-selectionBackground, .cm-selectionBackground, ::selection": {
      backgroundColor: "rgba(242, 184, 75, 0.22)",
    },
    ".cm-activeLine": { backgroundColor: "rgba(255,255,255,0.04)" },
    ".cm-gutters": {
      backgroundColor: "#0F2A2E",
      color: "#4F6C70",
      border: "none",
      paddingLeft: "6px",
    },
    ".cm-activeLineGutter": { backgroundColor: "transparent", color: "#9DB4B0" },
    ".cm-matchingBracket": {
      backgroundColor: "rgba(242,184,75,0.18)",
      outline: "1px solid rgba(242,184,75,0.45)",
    },
    ".cm-foldGutter": { display: "none" },
    ".cm-tooltip": {
      backgroundColor: "#143539",
      border: "1px solid #245459",
      color: "#E6EEEC",
      fontFamily: '"IBM Plex Mono", monospace',
    },
    ".cm-tooltip-autocomplete ul li[aria-selected]": { backgroundColor: "#1B4247" },
  },
  { dark: true },
);

const highlight = HighlightStyle.define([
  { tag: [t.keyword, t.controlKeyword, t.moduleKeyword, t.operatorKeyword], color: "#F2B84B" },
  { tag: [t.definitionKeyword, t.modifier], color: "#F2B84B" },
  { tag: [t.string, t.special(t.string), t.character], color: "#9FE1C3" },
  { tag: [t.number, t.bool, t.null, t.atom], color: "#FFB199" },
  { tag: [t.comment, t.lineComment, t.blockComment, t.docComment], color: "#7E9995", fontStyle: "italic" },
  { tag: [t.function(t.variableName), t.function(t.propertyName), t.macroName], color: "#8FD3F4" },
  { tag: [t.typeName, t.className, t.namespace, t.standard(t.typeName)], color: "#C9B8FF" },
  { tag: [t.variableName, t.propertyName, t.attributeName], color: "#E6EEEC" },
  { tag: [t.operator, t.punctuation, t.bracket, t.separator], color: "#B7C9C6" },
  { tag: [t.meta, t.processingInstruction, t.annotation], color: "#9DB4B0" },
  { tag: t.invalid, color: "#FF8F70" },
]);

export const editorTheme = [chrome, syntaxHighlighting(highlight)];

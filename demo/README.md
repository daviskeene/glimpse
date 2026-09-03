# Glimpse demo

The web playground and docs for [Glimpse](../README.md), live at
[glimpse.daviskeene.com](https://glimpse.daviskeene.com).

```sh
cp .env.example .env      # point VITE_GLIMPSE_API_URL at a running API
npm install
npm run dev               # http://localhost:5173
npm run build             # static output in dist/
```

Vite + React + TypeScript + Tailwind, with CodeMirror for the editor. Everything it shows
(languages, versions, limits, health) comes from the API it is pointed at.

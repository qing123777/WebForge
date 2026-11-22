// Static lint config used by the FYP notebook's run_eslint tool.
// Browser globals declared read-only: generated code is front-end only.
//
// The list below is deliberately COMPREHENSIVE. A short hand-picked set caused
// false `no-undef` errors: when the model generated correct code using a
// standard browser global that was simply missing here (e.g. KeyboardEvent,
// getComputedStyle, MutationObserver), ESLint flagged it as an error the model
// could not fix by editing correct code, so the fix loop burned its cap and the
// file "failed" linting. `no-undef` must only fire on genuinely undefined
// identifiers, so every standard browser global is declared read-only.
// ECMAScript built-ins (Promise, Map, Set, Symbol, ...) come from ecmaVersion.
export default [
  {
    languageOptions: {
      ecmaVersion: "latest",
      sourceType: "module",
      globals: {
        // ── Core window / document / navigation ──────────────────────────
        window: "readonly", self: "readonly", globalThis: "readonly",
        document: "readonly", navigator: "readonly", location: "readonly",
        history: "readonly", screen: "readonly", visualViewport: "readonly",
        console: "readonly", performance: "readonly", origin: "readonly",
        // ── Dialogs / framing ────────────────────────────────────────────
        alert: "readonly", confirm: "readonly", prompt: "readonly",
        print: "readonly", open: "readonly", close: "readonly",
        focus: "readonly", blur: "readonly", postMessage: "readonly",
        scroll: "readonly", scrollTo: "readonly", scrollBy: "readonly",
        getSelection: "readonly", getComputedStyle: "readonly",
        matchMedia: "readonly",
        // ── Storage ──────────────────────────────────────────────────────
        localStorage: "readonly", sessionStorage: "readonly",
        // ── Timers / scheduling ──────────────────────────────────────────
        setTimeout: "readonly", clearTimeout: "readonly",
        setInterval: "readonly", clearInterval: "readonly",
        requestAnimationFrame: "readonly", cancelAnimationFrame: "readonly",
        requestIdleCallback: "readonly", cancelIdleCallback: "readonly",
        queueMicrotask: "readonly",
        // ── Networking / data ────────────────────────────────────────────
        fetch: "readonly", XMLHttpRequest: "readonly", WebSocket: "readonly",
        EventSource: "readonly", Headers: "readonly", Request: "readonly",
        Response: "readonly", AbortController: "readonly",
        AbortSignal: "readonly", FormData: "readonly", URL: "readonly",
        URLSearchParams: "readonly", Blob: "readonly", File: "readonly",
        FileReader: "readonly", FileList: "readonly", DataTransfer: "readonly",
        TextEncoder: "readonly", TextDecoder: "readonly",
        structuredClone: "readonly", DOMParser: "readonly", crypto: "readonly",
        // ── Observers ────────────────────────────────────────────────────
        MutationObserver: "readonly", ResizeObserver: "readonly",
        IntersectionObserver: "readonly", PerformanceObserver: "readonly",
        // ── Events ───────────────────────────────────────────────────────
        Event: "readonly", CustomEvent: "readonly", UIEvent: "readonly",
        KeyboardEvent: "readonly", MouseEvent: "readonly",
        PointerEvent: "readonly", TouchEvent: "readonly",
        FocusEvent: "readonly", InputEvent: "readonly", WheelEvent: "readonly",
        DragEvent: "readonly", SubmitEvent: "readonly",
        ClipboardEvent: "readonly", AnimationEvent: "readonly",
        TransitionEvent: "readonly", PopStateEvent: "readonly",
        HashChangeEvent: "readonly", MessageEvent: "readonly",
        ErrorEvent: "readonly", ProgressEvent: "readonly",
        StorageEvent: "readonly", EventTarget: "readonly",
        // ── DOM node / element types ─────────────────────────────────────
        Node: "readonly", Element: "readonly", HTMLElement: "readonly",
        HTMLInputElement: "readonly", HTMLButtonElement: "readonly",
        HTMLFormElement: "readonly", HTMLSelectElement: "readonly",
        HTMLTextAreaElement: "readonly", HTMLAnchorElement: "readonly",
        HTMLImageElement: "readonly", HTMLDialogElement: "readonly",
        HTMLTemplateElement: "readonly", HTMLCanvasElement: "readonly",
        HTMLVideoElement: "readonly", HTMLAudioElement: "readonly",
        HTMLLabelElement: "readonly", HTMLOptionElement: "readonly",
        NodeList: "readonly", HTMLCollection: "readonly",
        DOMTokenList: "readonly", DocumentFragment: "readonly",
        ShadowRoot: "readonly", DOMRect: "readonly", Range: "readonly",
        Selection: "readonly", customElements: "readonly", CSS: "readonly",
        // ── Media / misc constructors ────────────────────────────────────
        Image: "readonly", Audio: "readonly", Option: "readonly",
        Notification: "readonly", Worker: "readonly",
        BroadcastChannel: "readonly", ClipboardItem: "readonly"
      }
    },
    rules: { "no-undef": "error", "no-unused-vars": "warn" }
  }
];

import type { CapacitorConfig } from "@capacitor/cli";

// appId follows Android's reverse-domain convention — change this before
// a real Play Store submission if a different domain is ever registered
// for this project; it only needs to be globally unique and stable once
// real users have installed a build under it (changing it later is
// effectively a new app from Android's point of view).
const config: CapacitorConfig = {
  appId: "com.aurum.app",
  appName: "Moneta",
  webDir: "dist",
  server: {
    // The native WebView serves the app from the fixed origin
    // "https://localhost" (Capacitor's default androidScheme), while the
    // backend it talks to is an arbitrary, user-configured address entered
    // in ServerSetupScreen (see lib/serverUrl.ts) — almost always a
    // *different* origin. Moneta's own README documents the default
    // self-hosted deployment as plain HTTP on http://localhost:3000 (no
    // TLS by default), and Android blocks all cleartext (HTTP) traffic
    // app-wide since API 28. Without this, the app cannot reach that
    // documented default deployment (or any other non-HTTPS install) at
    // all. Confirmed against the installed @capacitor/cli 8.5.1: this
    // `server.cleartext` flag is read by writeCordovaAndroidManifest()
    // (node_modules/@capacitor/cli/dist/cordova.js), which `npx cap sync`
    // runs unconditionally for the android platform and emits
    // android:usesCleartextTraffic="true" on the generated
    // capacitor-cordova-android-plugins module's manifest — Gradle's
    // manifest merger then carries that attribute into the main app's
    // compiled AndroidManifest.xml. This is a deliberate requirement of
    // Moneta's self-hosted, no-TLS-by-default model, not an oversight.
    cleartext: true,
  },
  plugins: {
    // Every fetch()/XMLHttpRequest call from ServerSetupScreen.tsx,
    // lib/auth.ts, api/client.ts and api/backup.ts targets that same
    // user-configured, cross-origin backend — from the WebView's point of
    // view this is a cross-origin request, which the backend's
    // AURUM_CORS_ORIGINS allowlist does not cover by default and the
    // WebView's own browser-level CORS enforcement would otherwise block.
    // CapacitorHttp (built into @capacitor/core, confirmed in
    // node_modules/@capacitor/cli/dist/declarations.d.ts's PluginsConfig)
    // routes fetch()/XMLHttpRequest through a native HTTP client instead
    // of the WebView's networking stack on native platforms, which
    // sidesteps browser-level CORS entirely (CORS is enforced by the
    // browser/WebView, not by a native HTTP client). Native-only: this
    // plugin only intercepts requests when running inside the actual
    // Capacitor native shell, so it has no effect on the web build.
    CapacitorHttp: {
      enabled: true,
    },
  },
};

export default config;

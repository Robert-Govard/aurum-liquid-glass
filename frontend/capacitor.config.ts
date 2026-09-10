import type { CapacitorConfig } from "@capacitor/cli";

// appId follows Android's reverse-domain convention — change this before
// a real Play Store submission if a different domain is ever registered
// for this project; it only needs to be globally unique and stable once
// real users have installed a build under it (changing it later is
// effectively a new app from Android's point of view).
const config: CapacitorConfig = {
  appId: "com.aurum.app",
  appName: "Aurum",
  webDir: "dist",
};

export default config;

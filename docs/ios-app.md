# BetWise on iOS — install now (PWA), ship to TestFlight later

## Install today — PWA / "Add to Home Screen" (no App Store, no Apple account)

BetWise is an installable web app. On an iPhone/iPad:

1. Open **https://betwise-casino-production.up.railway.app** in **Safari** (must be Safari — only Safari can install to the Home Screen on iOS).
2. Tap **Share** (the square-with-up-arrow).
3. Scroll down → **Add to Home Screen** → **Add**.
4. Launch it from the **BetWise** chip icon. It opens **fullscreen** (no Safari address bar), behaves like a native app, and stays signed in across launches.

This is driven by the web-app manifest (`frontend/public/manifest.json`) and the `apple-mobile-web-app-*` tags in `frontend/index.html`. Android/Chrome also offers **Install app** from the browser menu.

## Ship to TestFlight later — Capacitor (native shell)

TestFlight only distributes *native* iOS apps, so the web app is wrapped in **Capacitor** (a native WKWebView that loads BetWise). You do the final build on your **Mac**; everything else is config.

**Prereqs:** Apple Developer Program membership ($99/yr), a Mac with **Xcode**, **CocoaPods** (`sudo gem install cocoapods`).

One-time setup, from `frontend/`:

```bash
npm i -D @capacitor/cli @capacitor/core @capacitor/ios
npx cap init "BetWise" "app.betwise.casino" --web-dir=dist
```

Point the native shell at the live deployment — the thinnest setup, always up to date, no resubmit per web change. `frontend/capacitor.config.ts`:

```ts
import type { CapacitorConfig } from '@capacitor/cli';
const config: CapacitorConfig = {
  appId: 'app.betwise.casino',
  appName: 'BetWise',
  webDir: 'dist',
  server: { url: 'https://betwise-casino-production.up.railway.app', cleartext: false },
};
export default config;
```

Then:

```bash
npm run build      # builds dist/ (used if you bundle assets instead of server.url)
npx cap add ios
npx cap sync ios
npx cap open ios   # opens Xcode — Mac only
```

In Xcode: set the **Signing team** (your Apple Dev account), confirm the bundle id, target **Any iOS Device**, **Product → Archive**, then **Distribute App → TestFlight & App Store Connect → Upload**. After processing it shows up in App Store Connect → **TestFlight**; add yourself as an internal tester and install via the TestFlight app.

### Heads-up: App Review for a casino app

External TestFlight testers require a **Beta App Review**, and Apple scrutinizes "casino/gambling" apps. BetWise is **simulated, fake-money, no real-money gambling** — state that plainly in the App Store Connect description and in-app, and it clears review. (The manifest `description` already says it.)

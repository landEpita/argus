/** The VAPID public key, as PushManager.subscribe wants it. */
export function keyToBytes(base64url: string): Uint8Array {
  const padded = base64url
    .replace(/-/g, "+")
    .replace(/_/g, "/")
    .padEnd(Math.ceil(base64url.length / 4) * 4, "=");
  const raw = atob(padded);
  return Uint8Array.from(raw, (c) => c.charCodeAt(0));
}

/** PushSubscription.toJSON() → the channel config the API validates. */
export function subscriptionConfig(json: PushSubscriptionJSON): Record<string, string> {
  const { endpoint, keys } = json;
  if (!endpoint || !keys?.p256dh || !keys.auth) throw new Error("incomplete push subscription");
  return { endpoint, p256dh: keys.p256dh, auth: keys.auth };
}

export function pushSupported(w: Window | undefined): boolean {
  return Boolean(w && "serviceWorker" in w.navigator && "PushManager" in w && "Notification" in w);
}

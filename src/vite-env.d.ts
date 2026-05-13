/// <reference types="vite/client" />

declare global {
  interface Window {
    kiwi?: {
      pickDirectory: () => Promise<string | null>
      pickOutputFile: () => Promise<string | null>
    }
  }
}

export {}

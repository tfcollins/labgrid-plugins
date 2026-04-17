/// <reference types="vite/client" />

declare module "asciinema-player" {
  interface PlayerOptions {
    fit?: "width" | "height" | "both" | false;
    theme?: string;
    cols?: number;
    rows?: number;
    autoPlay?: boolean;
    loop?: boolean | number;
    speed?: number;
  }
  interface Player {
    dispose(): void;
  }
  export function create(src: string, container: HTMLElement, opts?: PlayerOptions): Player;
}

declare module "asciinema-player/dist/bundle/asciinema-player.css" {
  const content: string;
  export default content;
}

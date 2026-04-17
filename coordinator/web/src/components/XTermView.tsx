import { useEffect, useRef } from "react";
import { Terminal } from "xterm";
import { FitAddon } from "xterm-addon-fit";
import "xterm/css/xterm.css";

interface Props {
  wsUrl: string;
  onClose?: (code: number) => void;
}

export default function XTermView({ wsUrl, onClose }: Props) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const term = new Terminal({
      cursorBlink: true,
      fontFamily: "monospace",
      fontSize: 13,
      theme: { background: "#1a1a1a" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    fit.fit();

    const ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";

    ws.onmessage = (ev) => {
      if (typeof ev.data === "string") {
        term.write(ev.data);
      } else {
        term.write(new Uint8Array(ev.data));
      }
    };
    ws.onclose = (ev) => {
      term.write(`\r\n[connection closed: ${ev.code}]\r\n`);
      onClose?.(ev.code);
    };

    const enc = new TextEncoder();
    const onData = (data: string) => {
      if (ws.readyState === WebSocket.OPEN) {
        ws.send(enc.encode(data));
      }
    };
    term.onData(onData);

    const onResize = () => fit.fit();
    window.addEventListener("resize", onResize);

    return () => {
      window.removeEventListener("resize", onResize);
      ws.close();
      term.dispose();
    };
  }, [wsUrl, onClose]);

  return <div ref={containerRef} style={{ width: "100%", height: "100%" }} />;
}

import { useEffect, useState } from "react";
import Pet from "./pet/Pet";
import Panel from "./panel/Panel";
import Fireworks from "./fireworks/Fireworks";

export type Route = "pet" | "panel" | "fireworks";

function parseRoute(hash: string): Route {
  const h = hash.replace(/^#\/?/, "");
  if (h.startsWith("panel")) return "panel";
  if (h.startsWith("fireworks")) return "fireworks";
  return "pet";
}

export default function App() {
  const [route, setRoute] = useState<Route>(() =>
    parseRoute(window.location.hash),
  );

  useEffect(() => {
    const onChange = () => setRoute(parseRoute(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  if (route === "panel") return <Panel />;
  if (route === "fireworks") return <Fireworks />;
  return <Pet />;
}

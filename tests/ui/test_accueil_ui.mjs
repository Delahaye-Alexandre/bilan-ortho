// Écran d'accueil (app/static/accueil.html), ouvert par le lanceur avant que
// le serveur réponde : il sonde /api/status et bascule sur l'application dès
// qu'elle répond ; après deux minutes muettes, il le dit et s'arrête.
// Lancer : bun tests/ui/test_accueil_ui.mjs
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register();

const HTML_PATH = new URL("../../app/static/accueil.html", import.meta.url).pathname;
const html = await Bun.file(HTML_PATH).text();
const scriptStart = html.indexOf("<script>");
const scriptEnd = html.indexOf("</script>");
const body = html.slice(scriptStart + "<script>".length, scriptEnd);
document.documentElement.innerHTML = html.slice(0, scriptStart) + html.slice(scriptEnd + "</script>".length);

let failures = 0;
const check = (label, cond) => {
  console.log(`${cond ? "OK   " : "ECHEC"} ${label}`);
  if (!cond) failures++;
};
const settle = () => new Promise((r) => setTimeout(r, 5));

// Le script de la page, avec ses dépendances d'environnement remplacées :
// `location` (adresse + bascule), `fetch`, `setTimeout` (minuteries capturées,
// déclenchées à la main) et `Date` (horloge pilotée).
function lancer({ search = "", fetchImpl, horloge = () => 0 }) {
  const loc = { search, remplacee: null, replace(u) { this.remplacee = u; } };
  const minuteries = [];
  const faussesMinuteries = (fn, ms) => { minuteries.push({ fn, ms }); return minuteries.length; };
  const appels = [];
  const fetchTrace = (u, o) => { appels.push({ u, o }); return fetchImpl(u, o); };
  new Function("location", "fetch", "setTimeout", "Date", body)(loc, fetchTrace, faussesMinuteries, { now: horloge });
  return { loc, minuteries, appels };
}
const refuse = () => Promise.reject(new TypeError("Failed to fetch"));
const opaque = () => Promise.resolve({ type: "opaque" });

// 1. Serveur déjà prêt : bascule immédiate sur l'application, port de l'adresse.
let t = lancer({ search: "?port=8765", fetchImpl: opaque });
await settle();
check("serveur prêt : bascule sur l'application (port lu dans l'adresse)",
  t.loc.remplacee === "http://127.0.0.1:8765/");
check("sonde /api/status en mode no-cors, sans cache",
  t.appels[0].u === "http://127.0.0.1:8765/api/status"
  && t.appels[0].o.mode === "no-cors" && t.appels[0].o.cache === "no-store");
check("sans port dans l'adresse : 8000", lancer({ fetchImpl: opaque }).appels[0].u.startsWith("http://127.0.0.1:8000/"));

// 2. Serveur en cours de démarrage : on ressonde toutes les 250 ms, puis bascule.
let restants = 2;
t = lancer({ search: "?port=8000", fetchImpl: () => (restants-- > 0 ? refuse() : opaque()) });
await settle();
check("connexion refusée : nouvelle sonde programmée à 250 ms, pas de bascule",
  t.loc.remplacee === null && t.minuteries.length === 1 && t.minuteries[0].ms === 250);
t.minuteries.shift().fn(); await settle();
t.minuteries.shift().fn(); await settle();
check("dès que le serveur répond : bascule", t.loc.remplacee === "http://127.0.0.1:8000/" && t.appels.length === 3);

// 3. Serveur muet deux minutes : le dire, avec où chercher, et cesser de sonder.
let maintenant = 0;
t = lancer({ search: "?port=8000", fetchImpl: refuse, horloge: () => maintenant });
await settle();
maintenant = 121000;
t.minuteries.shift().fn(); await settle();
const err = document.getElementById("err");
check("après 2 minutes : message d'échec visible, journal indiqué, plus de sonde",
  !err.hidden && err.textContent.includes("2 minutes") && err.textContent.includes("serveur.log")
  && document.getElementById("msg").textContent.includes("n'a pas démarré")
  && t.minuteries.length === 0 && t.loc.remplacee === null);

console.log(failures ? `\n${failures} échec(s)` : "\nTous les scénarios passent.");
process.exit(failures ? 1 : 0);

// Test fonctionnel du système de mise à jour côté page : information affichée
// une fois (vérification automatique active par défaut), bandeau avec
// nouveautés, « Ignorer cette version », installation en un clic (progression
// NDJSON, sauvegarde, écran d'attente). Charge la vraie page dans happy-dom.
// Lancer : bun tests/ui/test_maj_ui.mjs
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register();

const HTML_PATH = new URL("../../app/static/index.html", import.meta.url).pathname;
const html = await Bun.file(HTML_PATH).text();
const scriptStart = html.indexOf("<script>");
const scriptEnd = html.indexOf("</script>");
const scriptBody = html.slice(scriptStart + "<script>".length, scriptEnd);
document.documentElement.innerHTML = html.slice(0, scriptStart) + html.slice(scriptEnd + "</script>".length);

// --- Stub réseau ---------------------------------------------------------------
const appels = [];
const MAJ = {
  version_actuelle: "1.9.0", version_disponible: "9.9.9", maj_disponible: true,
  url: "https://github.com/Delahaye-Alexandre/bilan-ortho/releases/latest",
  notes: "• Texte riche dans les rubriques.\n• Mises à jour en un clic.",
  publiee_le: "2026-09-03", installation_possible: true, ignoree: false, verifiee_le: "2026-09-03T10:00:00+00:00",
};
let etat = { info_vue: false, ignoree: "", derniere: "" };
let versionServeur = "1.9.0";
const enc = new TextEncoder();
const flux = (lignes) => new Response(new ReadableStream({
  start(c) { for (const l of lignes) c.enqueue(enc.encode(JSON.stringify(l) + "\n")); c.close(); },
}), { status: 200, headers: { "Content-Type": "application/x-ndjson" } });
const json = (o, status = 200) => ({ ok: status < 400, status, statusText: "", json: async () => o });

globalThis.fetch = async (p, o = {}) => {
  const url = String(p);
  appels.push({ url, method: o.method || "GET", body: o.body ? JSON.parse(o.body) : null });
  if (url.startsWith("/api/config") && (o.method || "GET") === "GET") return json({ maj: { verification_auto: true }, style: {}, llm: {}, stt: { hotwords: [], corrections: {} }, embeddings: {}, rgpd: {}, sauvegarde: {}, praticien: {}, seuils: {}, cotation: {}, trame: { sections: [] }, catalogues: {}, prompts: {} });
  if (url === "/api/config" && o.method === "PUT") return json({ maj: { verification_auto: false } });
  if (url === "/api/maj/etat" && o.method === "PUT") { Object.assign(etat, JSON.parse(o.body)); return json(etat); }
  if (url === "/api/maj/etat") return json(etat);
  if (url.startsWith("/api/maj?auto=1")) return json(MAJ);
  if (url === "/api/maj") return json(MAJ);
  if (url === "/api/maj/telecharger") return flux([
    { etape: "sommes" }, { etape: "telechargement", recu: 0, total: 80000000 },
    { etape: "telechargement", recu: 40000000, total: 80000000 }, { etape: "verification" },
    { fini: true, fichier: "BilanOrtho-Setup-9.9.9.exe", octets: 80000000 },
  ]);
  if (url === "/api/maj/installer") { versionServeur = "9.9.9"; return json({ lance: true, sauvegarde: "C:\\Users\\x\\bilan-ortho\\sauvegardes\\bilan-ortho-20260903.db", version: "9.9.9" }); }
  if (url.startsWith("/api/status")) return json({ db_exists: true, unlocked: true, version: versionServeur });
  return json({});
};
globalThis.confirm = () => true;
let alertes = [];
globalThis.alert = (m) => alertes.push(m);
let recharge = 0;
try { Object.defineProperty(window.location, "reload", { value: () => { recharge++; }, configurable: true }); } catch {}

const body = scriptBody.replace(/gate\(\);\s*$/, "") + `
;globalThis.__t = {
  get QUITTER_SANS_GARDE() { return QUITTER_SANS_GARDE; },
  get MAJ() { return MAJ; },
  verifierMajAuto, verifierMaj, installerMaj, saisieEnCours,
};`;
new Function(body)();
const __t = globalThis.__t;

let failures = 0;
const check = (label, cond) => { console.log(`${cond ? "OK   " : "ECHEC"} ${label}`); if (!cond) failures++; };
const settle = async (n = 3) => { for (let i = 0; i < n; i++) await new Promise((r) => setTimeout(r, 0)); };
const g = (id) => document.getElementById(id);

// === 1. Vérification automatique : information une fois + bandeau enrichi ======
await __t.verifierMajAuto(); await settle();
check("information affichée (vérification active par défaut, info_vue absent)", g("majInfoBanner").hidden === false);
check("vérification automatique : /api/maj?auto=1", appels.some((a) => a.url === "/api/maj?auto=1"));
check("bandeau : version, date publiée", g("majBanner").hidden === false && g("majVersion").textContent === "9.9.9"
  && g("majDate").textContent.includes("03/09/2026"));
check("bandeau : nouveautés en texte (jamais interprétées)", g("majNotesBloc").hidden === false
  && g("majNotes").textContent.includes("Mises à jour en un clic") && !g("majNotes").querySelector("*"));
check("bandeau : « Installer maintenant » visible quand l'app Windows le permet", g("majInstaller").hidden === false && g("majManuel").hidden === true);

g("majInfoOk").click(); await settle();
check("« Compris » : info_vue enregistré, bandeau d'information masqué",
  appels.some((a) => a.url === "/api/maj/etat" && a.method === "PUT" && a.body.info_vue === true) && g("majInfoBanner").hidden === true);

// « Désactiver » : info vue ET réglage coupé.
etat.info_vue = false; appels.length = 0;
await __t.verifierMajAuto(); await settle();
g("majInfoDesactiver").click(); await settle();
check("« Désactiver » : réglage maj.verification_auto passé à false",
  appels.some((a) => a.url === "/api/config" && a.method === "PUT" && a.body.overrides.maj.verification_auto === false));

// === 2. Ignorer cette version / Plus tard ========================================
g("majIgnorer").click(); await settle();
check("« Ignorer cette version » : enregistré, bandeau masqué",
  appels.some((a) => a.url === "/api/maj/etat" && a.method === "PUT" && a.body.ignoree === "9.9.9") && g("majBanner").hidden === true);
// Au démarrage suivant, la version ignorée ne fait plus de bandeau ; à la demande, si, en le disant.
MAJ.ignoree = true;
await __t.verifierMaj(true); await settle();
check("version ignorée : pas de bandeau en automatique", g("majBanner").hidden === true);
await __t.verifierMaj(false); await settle();
check("version ignorée : bandeau à la demande, avec la mention", g("majBanner").hidden === false && g("majIgnoree").hidden === false);
MAJ.ignoree = false;
g("majPlusTard").click();
check("« Plus tard » masque le bandeau", g("majBanner").hidden === true);

// === 3. Poste sans installation possible : lien seul ==============================
MAJ.installation_possible = false;
await __t.verifierMaj(false); await settle();
check("dépôt cloné / autre OS : bouton d'installation absent, explication affichée",
  g("majInstaller").hidden === true && g("majManuel").hidden === false);
check("dépôt cloné / autre OS : le lien de téléchargement manuel est le seul chemin", g("majOuvrir").hidden === false);
MAJ.installation_possible = true;
await __t.verifierMaj(false); await settle();
check("installation intégrée possible : pas de lien vers GitHub, la mise à jour se fait dans l'application",
  g("majInstaller").hidden === false && g("majOuvrir").hidden === true);

// === 4. Installation en un clic ==================================================
// Travail non enregistré : refus explicite, rien n'est lancé.
g("dicteeText").value = "dictée non structurée";
appels.length = 0;
await __t.installerMaj(); await settle();
check("travail en cours : la mise à jour refuse de fermer l'application",
  alertes.length === 1 && !appels.some((a) => a.url === "/api/maj/telecharger"));
g("dicteeText").value = "";

await __t.installerMaj(); await settle(10);
const tele = appels.find((a) => a.url === "/api/maj/telecharger");
const inst = appels.find((a) => a.url === "/api/maj/installer");
check("téléchargement demandé pour la version proposée", !!tele && tele.body.version === "9.9.9");
check("installation demandée avec le port de cette page", !!inst && inst.body.version === "9.9.9" && inst.body.port === 8000);
check("progression : barre à 100 % après vérification", g("majBarre").style.width === "100%");
check("écran d'attente : sauvegarde nommée, reconnexion annoncée",
  g("majOverlay").hidden === false && g("majOverlayTexte").textContent.includes("bilan-ortho-20260903.db")
  && g("majOverlayTexte").textContent.includes("reconnectera"));
check("le rechargement ne déclenchera pas la garde « saisie en cours »", __t.QUITTER_SANS_GARDE === true);
await new Promise((r) => setTimeout(r, 4300));
check("nouvelle version détectée sur /api/status : page rechargée", recharge >= 1);

// === 5. Échec de téléchargement : message, lien manuel, rien lancé ================
appels.length = 0;
const fetchOk = globalThis.fetch;
globalThis.fetch = async (p, o = {}) => (String(p) === "/api/maj/telecharger"
  ? flux([{ etape: "sommes" }, { erreur: "La signature des empreintes ne correspond pas à la clé de publication de Bilan Ortho : installation refusée." }])
  : fetchOk(p, o));
g("majOverlay").hidden = true;
await __t.installerMaj(); await settle(10);
check("signature invalide : interruption expliquée, installeur jamais lancé",
  g("majEtape").textContent.includes("signature") && g("majEtape").textContent.includes("Télécharger")
  && !appels.some((a) => a.url === "/api/maj/installer"));
check("après un échec : le lien de téléchargement manuel réapparaît en secours", g("majOuvrir").hidden === false);

console.log(failures ? `\n${failures} scénario(s) en échec.` : "\nTous les scénarios passent.");
process.exit(failures ? 1 : 0);

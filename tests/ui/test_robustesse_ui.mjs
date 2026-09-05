// Test fonctionnel de la robustesse frontend (audit 2026-07-17, Lot 1) :
// - C2 : les rubriques modifiées non enregistrées survivent au re-rendu
// - C4 : réponse 423 → overlay de verrouillage ré-affiché, pas de crash
// - erreurs réseau traduites en français (wrapper api)
// - anti double-clic (newBilan) et analyse unique (STRUCTURING)
// - réponse tardive après changement de bilan : l'écran n'est pas écrasé
// Lancer : bun tests/ui/test_robustesse_ui.mjs
import { GlobalRegistrator } from "@happy-dom/global-registrator";

// L'aperçu de mise en page pose un PDF (blob:) dans un iframe : happy-dom ne
// doit pas tenter de le charger.
GlobalRegistrator.register({ settings: { disableIframePageLoading: true } });

const HTML_PATH = new URL("../../app/static/index.html", import.meta.url).pathname;
const html = await Bun.file(HTML_PATH).text();

const scriptStart = html.indexOf("<script>");
const scriptEnd = html.indexOf("</script>");
const scriptBody = html.slice(scriptStart + "<script>".length, scriptEnd);
const markup = html.slice(0, scriptStart) + html.slice(scriptEnd + "</script>".length);

document.documentElement.innerHTML = markup;

// --- Stub micro / MediaRecorder ----------------------------------------------
class FakeMediaRecorder {
  constructor(stream) { this.stream = stream; }
  // `state` comme le vrai MediaRecorder : la page ne stoppe que si
  // « recording » (un double-clic sur « Arrêter » lève sinon une DOMException).
  state = "inactive";
  start() { this.state = "recording"; }
  stop() {
    this.state = "inactive";
    if (this.ondataavailable) this.ondataavailable({ data: { size: 5 } });
    if (this.onstop) this.onstop();
  }
}
globalThis.MediaRecorder = FakeMediaRecorder;
const fakeStream = { getTracks: () => [{ stop() {} }] };
try {
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: async () => fakeStream }, configurable: true,
  });
} catch {
  navigator.mediaDevices = { getUserMedia: async () => fakeStream };
}

// --- Stub réseau -------------------------------------------------------------
const structureCalls = [];
let structureResponder = () => ({ bilan: null, questions: [] });
let bilanCreator = () => ({ id: "nb1", statut: "brouillon", domaines: [], epreuves: [], sections: [] });
let bilanCreates = 0;
let sectionPuts = [];
let sectionResponder = () => ({});
let holdNext = null;    // promesse pour tester l'état « en vol »
let reseauCoupe = false; // simule un serveur injoignable
let sauvegardeCalls = 0;
let recentsRequests = [];
let recentsResponder = () => [{ id: 7, statut: "brouillon", domaine_titres: "Générique" }];
let exportResponder = null;
let exportCalls = 0;
let statusCalls = 0;
let keepaliveCalls = 0;
let statutPuts = [];
let epreuvePosts = [], epreuveDeletes = [], bilanDeletes = 0;
let epreuveResponder = () => ({});
let statusResponder = () => ({ db_exists: true, unlocked: true, first_run: false, version: "1.8.0" });
let installResponder = () => ({ ollama: true, pret: true, config_lisible: true, modeles: [] });
let lockCalls = 0;
let passphrasePosts = [];
let pullPosts = [];
let whisperPosts = 0;
let transcribeKo = false;
let pullLignes = () => ['{"error":"pull model manifest: file does not exist"}'];
const fluxNdjson = (lignes) => new ReadableStream({
  start(ctrl) { ctrl.enqueue(new TextEncoder().encode(lignes.join("\n") + "\n")); ctrl.close(); },
});
// Abandon d'une requête via AbortController : le stub rejette comme fetch
// (erreur nommée AbortError) dès que le signal est levé.
const erreurAbandon = () => { const e = new Error("aborted"); e.name = "AbortError"; return e; };
const abandon = (signal) => new Promise((_, rej) => {
  if (!signal) return;
  if (signal.aborted) rej(erreurAbandon());
  signal.addEventListener("abort", () => rej(erreurAbandon()));
});
let restaurationCalls = [];
let restaurationResponder = () => ({ ok: true, fichier: "f", filet: "g" });
let editeurCalls = [];       // PUT/DELETE des routes /api/config/{trame,catalogues,prompts}
let analyses = [];           // POST /api/config/trame/analyse (reprise de trame, lot C)
const TRAME_PROPOSEE = [
  { cle: "anamnese", titre: "Anamnèse" }, { cle: "contexte_scolaire", titre: "Contexte scolaire" },
  { cle: "epreuves", titre: "Bilan analytique" },
];
let editeurResponder = null; // null = succès (config effective renvoyée)
let refsList = [];           // GET /api/references
let packPosts = 0, packDeletes = 0;
const SAUVEGARDES = {
  dossier: "", derniere: "2026-07-20 10:00:00",
  fichiers: [{ fichier: "bilan-ortho-sauvegarde-20260720-100000.db", octets: 4096 }],
};

const rep = (r) => r && r.__status
  ? { ok: false, status: r.__status, statusText: "ERR", json: async () => ({ detail: r.detail }) }
  : { ok: true, status: 200, json: async () => r, blob: async () => new Blob(["x"]) };

// Config effective complète (pour fillSettings) et surcharges partielles
// (pour l'éditeur Avancé — il ne doit afficher QUE les surcharges).
const CFG = {
  llm: { model: "qwen2.5:7b", temperature: 0.3 },
  stt: { device: "auto", model: "auto", beam_size: 5, vad: true, language: "fr", hotwords: [], corrections: {} },
  style: { few_shot_k: 4, niveau_detail: "standard", vouvoiement: true },
  embeddings: { model: "nomic-embed-text" },
  seuils: { fragilite_et: -1, pathologique_et: -1.5, severe_et: -2,
            fragilite_percentile: 16, pathologique_percentile: 7, severe_percentile: 2 },
  cotation: { valeur_amo: 2.6, bilan_simple_coeff: 24, bilan_complexe_coeff: 34, renouvellement_coeff: 30 },
  rgpd: { verrouillage_inactivite_minutes: 15, conservation_jours: 0 },
  sauvegarde: { dossier: "", retention: 10, auto_jours: 7 },
  trame: { sections: [{ cle: "anamnese", titre: "Anamnèse" }] },
  catalogues: {}, prompts: { structure_system: "" },
};
const OVERRIDES = { prompts: { structure_system: "MON PROMPT PERSO" } };

globalThis.fetch = async (p, o = {}) => {
  if (reseauCoupe) throw new TypeError("Failed to fetch");
  const url = String(p);
  // AVANT la branche « /structure » : l'URL de la consigne intégrée la contient
  if (url.includes("/api/prompts/structure-defaut"))
    return rep({ prompt: 'CONSIGNE INTÉGRÉE {cles} — réponds {"updates":[]}' });
  if (url.includes("/structure")) {
    structureCalls.push(JSON.parse(o.body));
    if (holdNext) await Promise.race([holdNext, abandon(o.signal)]);
    return rep(structureResponder());
  }
  if (url.endsWith("/api/lock")) { lockCalls++; return rep({ ok: true }); }
  if (url.includes("/api/installation/pull")) {
    pullPosts.push(JSON.parse(o.body));
    return { ok: true, status: 200, body: fluxNdjson(pullLignes()) };
  }
  if (url.endsWith("/api/passphrase")) {
    passphrasePosts.push(JSON.parse(o.body));
    return rep({ sauvegarde: { fichier: "s/bilan-ortho-sauvegarde-20260903-101500.db", octets: 4096 },
                 sauvegarde_erreur: "", anciennes_copies: 2 });
  }
  if (url.endsWith("/api/bilans") && o.method === "POST") {
    bilanCreates++;
    if (holdNext) await holdNext;
    return rep(bilanCreator());
  }
  if (url.includes("/statut")) {
    const b = JSON.parse(o.body);
    statutPuts.push(b);
    return rep({ ...structuredClone(CUR0), statut: b.statut });
  }
  if (url.includes("/export")) { exportCalls++; return rep(exportResponder ? exportResponder() : {}); }
  if (url.includes("/api/bilans?")) {
    const q = Object.fromEntries(url.split("?")[1].split("&").map((kv) => kv.split("=")));
    recentsRequests.push({ limit: +q.limit, offset: +q.offset });
    return rep(recentsResponder(+q.limit, +q.offset));
  }
  if (url.includes("/sections/")) {
    sectionPuts.push({ url, body: JSON.parse(o.body) });
    return rep(sectionResponder());
  }
  if (url.includes("/api/config/trame/analyse")) {
    analyses.push(o.body && o.body.get ? o.body.get("fichier") : null);
    return rep({ sections: structuredClone(TRAME_PROPOSEE), detection: "styles" });
  }
  const mEd = url.match(/\/api\/config\/(trame|catalogues|prompts)/);
  if (mEd) {
    editeurCalls.push({ cible: mEd[1], method: o.method, body: o.body ? JSON.parse(o.body) : null });
    return rep(editeurResponder ? editeurResponder() : structuredClone(CFG));
  }
  if (url.includes("/api/references/pack")) {
    if (o.method === "POST") {
      packPosts++;
      refsList = refsList.filter((r) => r.source !== "fictif").concat([
        { id: 101, titre: "Anamnèse", section_cle: "anamnese", source: "fictif" },
        { id: 102, titre: "Projet thérapeutique", section_cle: "projet", source: "fictif" },
      ]);
      return rep({ n_fichiers: 11, n_extraits: 2 });
    }
    if (o.method === "DELETE") {
      packDeletes++;
      const n = refsList.filter((r) => r.source === "fictif").length;
      refsList = refsList.filter((r) => r.source !== "fictif");
      return rep({ n });
    }
  }
  if (url.includes("/api/references")) {
    if (o.method === "POST") {
      return rep({ n: 3, sections: [], extraits_ecartes: 0, elements_caviardes: 0,
                   trame_proposee: { sections: structuredClone(TRAME_PROPOSEE), detection: "gras" } });
    }
    if (o.method === "DELETE") {
      refsList = refsList.filter((r) => r.id !== +url.split("/").pop());
      return rep({ ok: true });
    }
    return rep(refsList.map((r) => ({ ...r })));
  }
  if (url.includes("/api/transcribe"))
    return rep(transcribeKo ? { __status: 500, detail: "La transcription a échoué." } : { text: "texte transcrit" });
  if (url.includes("/api/installation/whisper")) { whisperPosts++; return rep({ etat: "en_cours", message: "", modele: "medium" }); }
  if (url.includes("/api/models")) return rep({ models: ["qwen3.5:4b", "qwen3.5:9b"], default: "qwen3.5:4b" });
  if (url.includes("/api/status")) { statusCalls++; return rep(statusResponder()); }
  if (url.includes("/api/keepalive")) { keepaliveCalls++; return rep({ ok: true }); }
  if (url.includes("/api/installation")) return rep(installResponder());
  if (url.includes("/epreuves")) {
    if (o.method === "DELETE") { epreuveDeletes.push(url); return rep(epreuveResponder(true)); }
    epreuvePosts.push(JSON.parse(o.body));
    return rep(epreuveResponder(false));
  }
  const mBil = url.match(/\/api\/bilans\/([\w-]+)$/);
  if (mBil && o.method === "DELETE") { bilanDeletes++; return rep({ ok: true }); }
  if (mBil && (!o.method || o.method === "GET")) {
    const b = structuredClone(CUR0); b.id = mBil[1]; return rep(b);
  }
  if (url.includes("/api/domaines"))
    return rep([{ cle: "langage_oral", titre: "Langage oral" }, { cle: "voix", titre: "Voix" }]);
  if (url.includes("/api/catalogues/"))
    return rep({ guidance: "Guidance intégrée langage oral.",
                 tests: [{ nom: "GRBAS", tranche: "", mesure: "voix", metriques: ["qualitatif"] }] });
  if (url.includes("/api/config/overrides")) return rep(structuredClone(OVERRIDES));
  if (url.includes("/api/config")) return rep(structuredClone(CFG));
  if (url.includes("/api/restauration")) {
    restaurationCalls.push(JSON.parse(o.body));
    if (holdNext) await holdNext;
    return rep(restaurationResponder());
  }
  if (url.includes("/api/sauvegardes")) return rep(structuredClone(SAUVEGARDES));
  if (url.includes("/api/sauvegarde") && o.method === "POST") {
    sauvegardeCalls++;
    if (holdNext) await holdNext;
    return rep({ fichier: "sauvegardes/bilan-ortho-sauvegarde-t.db", octets: 4096 });
  }
  return { ok: true, status: 200, json: async () => ({}) };
};

// --- Évaluation du script de la page (sans le gate() de démarrage) -----------
const body = scriptBody.replace(/gate\(\);\s*$/, "") + `
;globalThis.__t = {
  get QS() { return QS; }, set QS(v) { QS = v; },
  get CUR() { return CUR; }, set CUR(v) { CUR = v; },
  get QUITTER_SANS_GARDE() { return QUITTER_SANS_GARDE; }, set QUITTER_SANS_GARDE(v) { QUITTER_SANS_GARDE = v; },
  renderQuestions, renderBilan, structure, saisieEnCours, loadRecents, loadRefs,
  loadBilan, sectionsNonEnregistrees, gate, loadLLM, loadDomaines,
  rtVersMd, remplirEditeur, verifierVerrou, signalerActivite, delaiProchaineVerifS,
  get appStarted() { return appStarted; },
  set dernierSignalActivite(v) { dernierSignalActivite = v; },
  get INST_POLL_MS() { return INST_POLL_MS; }, set INST_POLL_MS(v) { INST_POLL_MS = v; },
};`;
new Function(body)();

const CUR0 = {
  id: "b1", statut: "brouillon", domaines: [], epreuves: [], patient: null,
  sections: [
    { cle: "anamnese", titre: "Anamnèse", statut: "vide", contenu: "Texte initial." },
    { cle: "diagnostic", titre: "Diagnostic", statut: "vide", contenu: "" },
  ],
};

const settle = () => new Promise((r) => setTimeout(r, 25));
let failures = 0;
const check = (label, cond) => {
  console.log(`${cond ? "OK   " : "ECHEC"} ${label}`);
  if (!cond) failures++;
};
const secTa = (cle) => document.querySelector(`#bilanView .sec[data-cle="${cle}"] .secText`);
// Zone éditable (texte riche) : lecture et écriture en Markdown restreint,
// comme l'application elle-même.
const lire = (cle) => __t.rtVersMd(secTa(cle));
const ecrire = (cle, v) => __t.remplirEditeur(secTa(cle), v);
const savest = (cle) => document.querySelector(`#bilanView .sec[data-cle="${cle}"] .savest`);
const status = () => document.getElementById("structStatus").textContent;
const overlay = () => document.getElementById("lockOverlay");

// === 1. C2 : une rubrique modifiée non enregistrée survit au re-rendu ========
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
check("rendu initial : contenu serveur affiché", lire("anamnese") === "Texte initial.");

ecrire("anamnese", "Texte initial. CORRIGÉ À LA MAIN");
structureResponder = () => {
  const b = structuredClone(CUR0);
  b.sections[0].contenu = "Texte initial.\n\nAjout proposé par l'IA.";
  return { bilan: b, questions: [] };
};
document.getElementById("dicteeText").value = "une dictée";
document.getElementById("structBtn").click();
await settle();
check("C2 : la correction manuelle non enregistrée est préservée après structuration",
  lire("anamnese") === "Texte initial. CORRIGÉ À LA MAIN");
check("C2 : l'utilisateur est prévenu (« non enregistrées »)",
  savest("anamnese").textContent.includes("non enregistrées"));
check("C2 : les rubriques non modifiées suivent le serveur",
  lire("diagnostic") === "");

// Après « Enregistrer », le brouillon devient la référence : plus d'alerte.
document.querySelector('#bilanView .sec[data-cle="anamnese"] .save').click();
await settle();
check("C2 : enregistrement du brouillon → PUT envoyé + statut ✓",
  sectionPuts.length === 1 && savest("anamnese").textContent === "✓");
__t.renderBilan();
await settle();
check("C2 : après enregistrement, re-rendu sans alerte ni perte",
  lire("anamnese") === "Texte initial. CORRIGÉ À LA MAIN"
  && !savest("anamnese").textContent.includes("non enregistrées"));

// === 2. Les brouillons ne fuient pas vers un autre bilan =====================
ecrire("anamnese", "BROUILLON DU BILAN 1");
const b2 = structuredClone(CUR0); b2.id = "b2"; b2.sections[0].contenu = "Contenu du bilan 2.";
__t.CUR = b2;
__t.renderBilan();
check("changement de bilan : aucun brouillon de l'ancien bilan n'apparaît",
  lire("anamnese") === "Contenu du bilan 2.");

// === 3. C4 : 423 (auto-verrouillage) → overlay ré-affiché, pas de crash ======
overlay().hidden = true;
structureResponder = () => ({ __status: 423, detail: "Application verrouillée." });
document.getElementById("dicteeText").value = "dictée après verrouillage";
document.getElementById("structBtn").click();
await settle();
check("C4 : 423 → l'overlay de verrouillage est ré-affiché", overlay().hidden === false);
check("C4 : message français explicite", status().includes("verrouillée"));
check("C4 : pas de crash — bouton Structurer ré-activé",
  !document.getElementById("structBtn").disabled);
check("C4 : la dictée n'est pas perdue en cas d'erreur",
  document.getElementById("dicteeText").value === "dictée après verrouillage");
overlay().hidden = true;

// === 4. Erreur réseau traduite en français ===================================
reseauCoupe = true;
document.getElementById("structBtn").click();
await settle();
reseauCoupe = false;
check("réseau coupé : message « serveur injoignable » (pas de « Failed to fetch »)",
  status().includes("injoignable") && !status().includes("Failed"));

// === 5. Anti double-clic : 2 clics rapides → 1 seul bilan créé ===============
// La dictée est vidée d'abord : changer de dossier avec une dictée en cours
// demande désormais confirmation (cf. scénario 27).
document.getElementById("dicteeText").value = "";
bilanCreates = 0;
holdNext = new Promise((r) => setTimeout(r, 60));
document.getElementById("newBilan").click();
document.getElementById("newBilan").click();
await new Promise((r) => setTimeout(r, 100));
holdNext = null;
check("double-clic « + Nouveau bilan » : un seul POST", bilanCreates === 1);

// === 6. Une seule analyse à la fois (Entrée/clics répétés) ===================
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
structureResponder = () => ({ bilan: structuredClone(CUR0), questions: [] });
const callsAvant = structureCalls.length;
holdNext = new Promise((r) => setTimeout(r, 60));
document.getElementById("dicteeText").value = "texte";
document.getElementById("structBtn").click();
document.getElementById("structBtn").click();
await new Promise((r) => setTimeout(r, 100));
holdNext = null;
check("clics répétés sur Structurer : un seul appel LLM",
  structureCalls.length === callsAvant + 1);

// === 7. Réponse tardive après changement de bilan : écran intact =============
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
structureResponder = () => {
  const b = structuredClone(CUR0);
  b.sections[0].contenu = "RÉSULTAT TARDIF DU BILAN 1";
  return { bilan: b, questions: [{ section: "", question: "Question tardive ?", pourquoi: "" }] };
};
holdNext = new Promise((r) => setTimeout(r, 60));
document.getElementById("dicteeText").value = "longue analyse";
document.getElementById("structBtn").click();
await new Promise((r) => setTimeout(r, 20));
const b9 = structuredClone(CUR0); b9.id = "b9"; b9.sections[0].contenu = "Bilan 9.";
__t.CUR = b9;
__t.renderBilan();
holdNext = null;
await new Promise((r) => setTimeout(r, 80));
check("réponse tardive : l'écran du nouveau bilan n'est pas écrasé",
  __t.CUR.id === "b9" && lire("anamnese") === "Bilan 9.");
check("réponse tardive : aucune question orpheline affichée",
  document.querySelectorAll("#questions .q").length === 0);
check("réponse tardive : l'utilisateur est informé du bilan de destination",
  status().includes("changé de bilan"));

// === 8. saisieEnCours (beforeunload) =========================================
document.getElementById("dicteeText").value = "";
__t.QS = []; __t.renderQuestions();
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
check("saisieEnCours : rien en cours → false", __t.saisieEnCours() === false);
document.getElementById("dicteeText").value = "dictée non structurée";
check("saisieEnCours : dictée transcrite non structurée → true", __t.saisieEnCours() === true);
document.getElementById("dicteeText").value = "";
ecrire("anamnese", "modif non enregistrée");
check("saisieEnCours : rubrique modifiée non enregistrée → true", __t.saisieEnCours() === true);

// === 9. Éditeurs dédiés : surcharges affichées, défauts jamais figés =========
document.getElementById("settingsBtn").click();
await settle();
check("modale Paramètres ouverte", document.getElementById("settingsOverlay").hidden === false);
check("éditeur consigne : la surcharge du praticien est affichée",
  document.getElementById("promptTexte").value === "MON PROMPT PERSO");
check("éditeur consigne : provenance « personnalisée » indiquée",
  document.getElementById("promptProv").textContent.includes("personnalisée"));
check("éditeur trame : la trame effective est affichée",
  document.querySelector("#trameListe .trTitre") !== null
  && document.querySelector("#trameListe .trTitre").value === "Anamnèse");
check("éditeur trame : provenance « intégrée » (aucune surcharge)",
  document.getElementById("trameProv").textContent.includes("intégrée"));
editeurCalls = [];
document.getElementById("trameSave").click();
await settle();
check("trame sans modification : aucun enregistrement (défauts jamais figés)",
  editeurCalls.length === 0
  && document.getElementById("trameStatus").textContent.includes("Aucune modification"));
check("modale : focus posé à l'ouverture (premier champ de « Mon cabinet »)",
  document.activeElement === document.getElementById("cfgPratPrenom"));

// === 10. Échap ferme la modale ===============================================
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
check("Échap : modale fermée", document.getElementById("settingsOverlay").hidden === true);

// === 11. Accessibilité : statuts annoncés, listes au clavier =================
check("a11y : zone de statut annoncée (role=status)",
  document.getElementById("structStatus").getAttribute("role") === "status");
await __t.loadRecents();
const lien = document.querySelector("#recents a[data-id]");
check("a11y : lien de bilan récent focusable au clavier (href)",
  lien !== null && lien.getAttribute("href") === "#");

// === 12. Effacer la dictée : confirmation si du texte serait perdu ===========
let confirmCalls = [];
let confirmReponse = false;
globalThis.confirm = (msg) => { confirmCalls.push(msg); return confirmReponse; };
document.getElementById("dicteeText").value = "texte précieux";
document.getElementById("dicteeClear").click();
check("effacer avec texte : confirmation demandée", confirmCalls.length === 1);
check("effacer refusé : le texte est intact",
  document.getElementById("dicteeText").value === "texte précieux");
confirmReponse = true;
document.getElementById("dicteeClear").click();
check("effacer confirmé : champ vidé", document.getElementById("dicteeText").value === "");
confirmCalls = [];
document.getElementById("dicteeClear").click();
check("effacer un champ déjà vide : pas de confirmation", confirmCalls.length === 0);

// === 13. Copier le bilan : retour visuel =====================================
let copie = null;
try {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: async (t) => { copie = t; } }, configurable: true,
  });
} catch {
  navigator.clipboard = { writeText: async (t) => { copie = t; } };
}
// id distinct : le brouillon laissé par le scénario 8 ne doit pas être repris
// (il déclencherait à juste titre la demande d'enregistrement du scénario 27).
const bcopie = structuredClone(CUR0); bcopie.id = "bcopie";
__t.CUR = bcopie;
__t.renderBilan();
document.getElementById("copyBilan").click();
await settle();
check("copier : le contenu des rubriques est copié",
  copie !== null && copie.includes("Texte initial."));
check("copier : statut ✓ affiché",
  document.getElementById("copyStatus").textContent.includes("Copié"));
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: async () => { throw new Error("refus navigateur"); } },
  configurable: true,
});
document.getElementById("copyBilan").click();
await settle();
check("copier en échec : message d'erreur français",
  document.getElementById("copyStatus").textContent.includes("impossible"));

// === 14. Double-clic « Sauvegarder maintenant » : un seul fichier créé =======
sauvegardeCalls = 0;
holdNext = new Promise((r) => setTimeout(r, 60));
document.getElementById("sauvBtn").click();
document.getElementById("sauvBtn").click();
await new Promise((r) => setTimeout(r, 100));
holdNext = null;
check("double-clic sauvegarde : un seul POST", sauvegardeCalls === 1);
check("sauvegarde : nom du fichier affiché",
  document.getElementById("sauvStatus").textContent.includes("bilan-ortho-sauvegarde"));

// === 15. Échappement : un titre de section hostile ne casse rien =============
const bx = structuredClone(CUR0);
bx.id = "bx"; // id distinct : les brouillons des scénarios précédents ne s'appliquent pas
bx.sections[0].titre = 'Anamnèse"<b>piège</b>';
__t.CUR = bx;
__t.renderBilan();
check("échappement : aucun élément HTML injecté via le titre",
  document.querySelector("#bilanView .sec .head h3 b") === null);
check("échappement : le titre est affiché tel quel",
  document.querySelector('#bilanView .sec[data-cle="anamnese"] h3')
    .textContent.includes('Anamnèse"<b>piège</b>'));
check("échappement : data-cle reste exploitable (rubrique retrouvée)",
  secTa("anamnese") !== null && lire("anamnese") === "Texte initial.");

// === 16. Export : un 423 ré-affiche l'écran de verrouillage ==================
overlay().hidden = true;
__t.CUR = structuredClone(CUR0);
exportResponder = () => ({ __status: 423, detail: "Application verrouillée." });
document.getElementById("expMd").click();
await settle();
check("export sur coffre verrouillé : overlay ré-affiché", overlay().hidden === false);
check("export sur coffre verrouillé : message français",
  document.getElementById("copyStatus").textContent.includes("verrouillée"));
overlay().hidden = true;
exportResponder = null;

// === 17. « Afficher plus » : offset envoyé, pages empilées sans doublon ======
recentsResponder = (limit, offset) => offset === 0
  ? Array.from({ length: 20 }, (_, i) =>
      ({ id: 40 - i, statut: "brouillon", domaine_titres: "Générique" }))
  // recouvrement volontaire : l'id 21 figure déjà en fin de page 1
  : [{ id: 21, statut: "brouillon", domaine_titres: "Générique" },
     { id: 20, statut: "brouillon", domaine_titres: "Générique" },
     { id: 19, statut: "brouillon", domaine_titres: "Générique" }];
recentsRequests = [];
await __t.loadRecents();
check("pagination : première page pleine + lien « afficher plus »",
  document.querySelectorAll("#recents a[data-id]").length === 20
  && document.querySelector("#recents a[data-plus]") !== null);
document.querySelector("#recents a[data-plus]").click();
await settle();
check("pagination : la requête suivante envoie offset=20",
  recentsRequests.length === 2 && recentsRequests[1].offset === 20);
check("pagination : pages empilées sans doublon",
  document.querySelectorAll("#recents a[data-id]").length === 22);
check("pagination : lien masqué quand la page reçue n'est pas pleine",
  document.querySelector("#recents a[data-plus]") === null);

// === 18. Modales : role=dialog, aria-modal, piège de focus ===================
document.getElementById("settingsBtn").click();
await settle();
const modal = document.querySelector("#settingsOverlay .modal");
check("a11y : role=dialog + aria-modal sur la modale ouverte",
  modal.getAttribute("role") === "dialog" && modal.getAttribute("aria-modal") === "true");
const titreId = modal.getAttribute("aria-labelledby");
check("a11y : aria-labelledby pointe le titre existant",
  titreId !== null && document.getElementById(titreId).textContent.includes("Paramètres"));
// Même filtre que la page : le bloc « Réglages techniques » est replié
// (conteneur [hidden]), ses champs ne sont pas atteignables au clavier.
const focusables = [...modal.querySelectorAll("button, input, select, textarea, a[href]")]
  .filter((el) => !el.disabled && !el.hidden && !el.closest("[hidden]"));
focusables[focusables.length - 1].focus();
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
check("a11y : Tab depuis le dernier élément revient au premier (piège)",
  document.activeElement === focusables[0]);
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", shiftKey: true, bubbles: true }));
check("a11y : Shift+Tab depuis le premier va au dernier",
  document.activeElement === focusables[focusables.length - 1]);
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

// === 19. Analyse depuis le panneau de questions : statut près du bouton ======
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
__t.QS = [{ id: 991, section: "", question: "Question du panneau ?", pourquoi: "" }];
__t.renderQuestions();
structureResponder = () => ({ bilan: structuredClone(CUR0), questions: [] });
holdNext = new Promise((r) => setTimeout(r, 60));
const qel = document.querySelector('#questions .q[data-id="991"]');
qel.querySelector(".ans").value = "ma réponse";
qel.querySelector(".ansBtn").click();
await new Promise((r) => setTimeout(r, 20));
check("analyse depuis le panneau : statut visible près des questions",
  document.querySelector("#questions .qStatus").textContent.includes("Analyse en cours"));
check("analyse : spinner affiché dans le statut principal",
  document.querySelector("#structStatus .spin") !== null);
holdNext = null;
await new Promise((r) => setTimeout(r, 80));

// === 20. Restauration guidée : liste, passphrase exigée, un seul POST ========
try {
  Object.defineProperty(window.location, "reload", { value: () => {}, configurable: true });
} catch {}
document.getElementById("settingsBtn").click();
await settle();
const ligneRest = document.querySelector("#sauvListe [data-rest]");
check("restauration : la sauvegarde est listée (nom + taille)",
  ligneRest !== null
  && document.getElementById("sauvListe").textContent.includes("bilan-ortho-sauvegarde-20260720-100000.db")
  && document.getElementById("sauvListe").textContent.includes("4 Ko"));
ligneRest.click();
check("restauration : parcours guidé ouvert avec l'explication et le nom",
  document.getElementById("restZone").hidden === false
  && document.getElementById("restZone").textContent.includes("remplace toutes les données actuelles")
  && document.getElementById("restNom").textContent === "bilan-ortho-sauvegarde-20260720-100000.db");
document.getElementById("restConfirm").click();
await settle();
check("restauration : refus sans passphrase, aucun appel serveur",
  restaurationCalls.length === 0
  && document.getElementById("restStatus").textContent.includes("Saisissez la passphrase"));
document.getElementById("restPass").value = "ma phrase secrète";
holdNext = new Promise((r) => setTimeout(r, 60));
document.getElementById("restConfirm").click();
document.getElementById("restConfirm").click();
await new Promise((r) => setTimeout(r, 100));
holdNext = null;
check("restauration : double-clic → un seul POST", restaurationCalls.length === 1);
check("restauration : corps exact {fichier, passphrase}",
  restaurationCalls[0]
  && restaurationCalls[0].fichier === "bilan-ortho-sauvegarde-20260720-100000.db"
  && restaurationCalls[0].passphrase === "ma phrase secrète");
check("restauration : succès annoncé + rechargement programmé",
  document.getElementById("restStatus").textContent.includes("va se recharger"));

// === 21. Restauration : erreurs traduites, pas de rechargement ===============
restaurationCalls = [];
restaurationResponder = () => ({ __status: 400,
  detail: "Impossible d'ouvrir cette sauvegarde avec la passphrase saisie." });
document.querySelector("#sauvListe [data-rest]").click();
document.getElementById("restPass").value = "mauvaise";
document.getElementById("restConfirm").click();
await settle();
check("restauration en échec : message français affiché",
  document.getElementById("restStatus").textContent.includes("Impossible d'ouvrir"));
check("restauration en échec : bouton ré-activé",
  !document.getElementById("restConfirm").disabled);
overlay().hidden = true;
restaurationResponder = () => ({ __status: 423, detail: "Application verrouillée." });
document.getElementById("restPass").value = "x";
document.getElementById("restConfirm").click();
await settle();
check("restauration sur coffre verrouillé : overlay ré-affiché", overlay().hidden === false);
overlay().hidden = true;
restaurationResponder = () => ({ ok: true });
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

// === 22. Éditeur de trame : ajout, réordonnancement, avertissement ==========
document.getElementById("settingsBtn").click();
await settle();
document.getElementById("trameAdd").click();
const ligneAjoutee = [...document.querySelectorAll("#trameListe .ed-ligne")].pop();
ligneAjoutee.querySelector(".trCle").value = "epreuves";
ligneAjoutee.querySelector(".trTitre").value = "Épreuves";
ligneAjoutee.querySelector("[data-tr-up]").click();
editeurCalls = [];
document.getElementById("trameSave").click();
await settle();
check("trame : PUT avec la liste exacte réordonnée",
  editeurCalls.length === 1 && editeurCalls[0].cible === "trame"
  && editeurCalls[0].method === "PUT"
  && JSON.stringify(editeurCalls[0].body.sections) === JSON.stringify([
    { cle: "epreuves", titre: "Épreuves" }, { cle: "anamnese", titre: "Anamnèse" }]));
check("trame : provenance passée à « personnalisée » après enregistrement",
  document.getElementById("trameProv").textContent.includes("personnalisée"));
document.querySelector("#trameListe [data-tr-del]").click(); // supprime « epreuves »
check("trame : avertissement « epreuves » affiché (non bloquant)",
  document.getElementById("trameAvert").textContent.includes("epreuves"));
editeurCalls = [];
document.getElementById("trameSave").click();
await settle();
check("trame : l'enregistrement passe malgré l'avertissement",
  editeurCalls.length === 1
  && JSON.stringify(editeurCalls[0].body.sections)
     === JSON.stringify([{ cle: "anamnese", titre: "Anamnèse" }]));

// === 22 bis. Reprendre la trame d'un de mes bilans (lot C) ==================
const trameFichier = document.getElementById("trameFichier");
Object.defineProperty(trameFichier, "files", { value: [new File(["x"], "bilan.docx")], configurable: true });
editeurCalls = [];
trameFichier.dispatchEvent(new Event("change", { bubbles: true }));
await settle();
check("reprise : le document part à l'analyse, rien n'est enregistré",
  analyses.length === 1 && analyses[0] && analyses[0].name === "bilan.docx" && editeurCalls.length === 0);
const titresTrame = () => [...document.querySelectorAll("#trameListe .trTitre")].map((i) => i.value).join("|");
const clesTrame = () => [...document.querySelectorAll("#trameListe .trCle")].map((i) => i.value).join("|");
check("reprise : les intitulés du document remplacent la liste en édition, dans l'ordre, avec leurs clés",
  titresTrame() === "Anamnèse|Contexte scolaire|Bilan analytique" && clesTrame() === "anamnese|contexte_scolaire|epreuves");
check("reprise : le statut dit d'où viennent les rubriques et invite à enregistrer",
  document.getElementById("trameDepuisSt").textContent.includes("3 rubriques reprises")
  && document.getElementById("trameDepuisSt").textContent.includes("titres du document")
  && document.getElementById("trameDepuisSt").textContent.includes("Enregistrer la trame"));
document.getElementById("trameSave").click();
await settle();
check("reprise : « Enregistrer la trame » envoie la liste reprise telle quelle",
  editeurCalls.length === 1 && editeurCalls[0].method === "PUT"
  && JSON.stringify(editeurCalls[0].body.sections) === JSON.stringify(TRAME_PROPOSEE));

// === 23. Éditeur de catalogues : PUT complet, retour à l'intégré =============
check("catalogues : le domaine affiche le catalogue intégré (guidance + tests)",
  document.getElementById("catGuidance").value.includes("Guidance intégrée")
  && document.querySelector("#catTests .ctNom") !== null
  && document.querySelector("#catTests .ctNom").value === "GRBAS");
document.getElementById("catGuidance").value = "Ma guidance à moi.";
editeurCalls = [];
document.getElementById("catSave").click();
await settle();
check("catalogues : PUT du dict complet avec le domaine modifié",
  editeurCalls.length === 1 && editeurCalls[0].cible === "catalogues"
  && editeurCalls[0].body.langage_oral
  && editeurCalls[0].body.langage_oral.guidance === "Ma guidance à moi.");
check("catalogues : domaine marqué « personnalisé » dans la liste",
  document.querySelector("#catDomaine option").textContent.includes("personnalisé"));
confirmReponse = true;
editeurCalls = [];
document.getElementById("catRetour").click();
await settle();
check("catalogues : retour à l'intégré → domaine absent du corps envoyé",
  editeurCalls.length === 1 && editeurCalls[0].cible === "catalogues"
  && editeurCalls[0].method === "PUT"
  && !("langage_oral" in editeurCalls[0].body));
check("catalogues : le catalogue intégré est rechargé",
  document.getElementById("catGuidance").value.includes("Guidance intégrée"));

// === 24. Éditeur de consigne : défaut exposé, vide = DELETE, erreur ==========
document.getElementById("promptDefaut").click();
await settle();
check("consigne : préremplissage depuis la consigne intégrée exposée",
  document.getElementById("promptTexte").value.includes("CONSIGNE INTÉGRÉE {cles}"));
document.getElementById("promptTexte").value = "";
editeurCalls = [];
document.getElementById("promptSave").click();
await settle();
check("consigne vidée : DELETE émis (jamais de surcharge vide)",
  editeurCalls.length === 1 && editeurCalls[0].cible === "prompts"
  && editeurCalls[0].method === "DELETE");
check("consigne : provenance repassée à « intégrée »",
  document.getElementById("promptProv").textContent.includes("intégrée"));
editeurResponder = () => ({ __status: 422, detail: "donnée invalide (structure_system)" });
document.getElementById("promptTexte").value = "NOUVELLE CONSIGNE";
document.getElementById("promptSave").click();
await settle();
check("consigne : erreur serveur → message français dans le statut",
  document.getElementById("promptStatus").textContent.includes("Erreur : donnée invalide"));
editeurResponder = null;
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

// === 25. Écran d'aide : formulaires de retour ================================
// Règle produit : l'application n'émet jamais rien d'elle-même vers l'extérieur.
// Les liens de retour s'ouvrent sur clic seulement, vers le dépôt du projet, et
// l'URL est écrite en dur dans la page (jamais reprise d'une réponse réseau).
const ouvertures = [];
globalThis.open = (url, cible) => { ouvertures.push({ url, cible }); return null; };
document.getElementById("helpBtn").click();
await settle();
check("aide : ouvrir l'écran n'ouvre rien vers l'extérieur",
  ouvertures.length === 0);
document.getElementById("aideRetourLien").click();
document.getElementById("aideBugLien").click();
check("aide : les deux boutons ouvrent un formulaire du dépôt du projet",
  ouvertures.length === 2
  && ouvertures.every((o) =>
       o.url.startsWith("https://github.com/Delahaye-Alexandre/bilan-ortho/issues/new")
       && o.cible === "_blank")
  && ouvertures[0].url.includes("retour-de-test.yml")
  && ouvertures[1].url.includes("bug.yml"));
check("aide : un courriel reste proposé (sans compte GitHub)",
  !!document.querySelector('#helpOverlay a[href^="mailto:"]'));
check("aide : l'avertissement « aucun élément identifiant » accompagne les liens",
  document.getElementById("helpOverlay").textContent.includes("aucun élément identifiant"));

// === 26. Bilans de référence : pack d'exemples (charger / badge / retirer) ===
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
const refList = () => document.getElementById("refList");
const refStatus = () => document.getElementById("refStatus").textContent;
refsList = [{ id: 1, titre: "Mon anamnèse", section_cle: "anamnese", source: "import" }];
await __t.loadRefs();
check("références : l'import du praticien s'affiche sans badge « exemple »",
  refList().textContent.includes("Mon anamnèse")
  && !refList().textContent.includes("exemple"));
check("références : pas de lien de retrait sans pack chargé",
  !document.getElementById("refPackRetirer"));

document.getElementById("refPack").click();
await settle();
check("pack : un clic → un POST, statut ✓ avec le compte d'extraits",
  packPosts === 1 && refStatus().includes("✓") && refStatus().includes("11 bilans fictifs"));
check("pack : les extraits fictifs portent le badge « exemple »",
  refList().textContent.includes("exemple"));
check("pack : le lien « Retirer les exemples » apparaît",
  !!document.getElementById("refPackRetirer"));

document.getElementById("refPackRetirer").click();
await settle();
check("retrait : DELETE envoyé, exemples retirés, import du praticien conservé",
  packDeletes === 1 && !refList().textContent.includes("exemple")
  && refList().textContent.includes("Mon anamnèse")
  && !document.getElementById("refPackRetirer"));

reseauCoupe = true;
document.getElementById("refPack").click();
await settle();
check("pack : erreur réseau → message français dans le statut, pas de crash",
  refStatus().startsWith("Erreur"));
reseauCoupe = false;

// === 26 bis. Import d'un bilan : lien « Reprendre sa trame » (lot C) ========
const refFichier = document.getElementById("refFile");
Object.defineProperty(refFichier, "files", { value: [new File(["x"], "mon-bilan.docx")], configurable: true });
editeurCalls = [];
document.getElementById("refImport").click();
await settle();
const lienTrame = [...document.querySelectorAll("#refStatus a")].find((a) => a.textContent.includes("Reprendre sa trame"));
check("import : le statut propose de reprendre la trame du document, avec le compte de rubriques",
  refStatus().startsWith("✓ 3 extrait(s)") && !!lienTrame && lienTrame.textContent.includes("3 rubriques"));
check("import : rien n'est appliqué sans clic sur le lien", editeurCalls.length === 0);
lienTrame.click();
await settle(); await settle();
check("lien : les Paramètres s'ouvrent avec la trame du document en édition, non enregistrée",
  document.getElementById("settingsOverlay").hidden === false && editeurCalls.length === 0
  && clesTrame() === "anamnese|contexte_scolaire|epreuves"
  && document.getElementById("trameDepuisSt").textContent.includes("du bilan importé")
  && document.getElementById("trameDepuisSt").textContent.includes("lignes en gras"));
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));

// === 27. Corrections en cours : rien ne part sans elles (audit 08-11, 1.1) ===
// Export, copie et validation lisaient le contenu enregistré, jamais les zones
// de saisie : une correction tapée mais non enregistrée partait à la trappe.
globalThis.URL.createObjectURL = () => "blob:test";
globalThis.URL.revokeObjectURL = () => {};
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
await settle();
ecrire("anamnese", "Texte initial. CORRECTION CLINIQUE");
check("détection : la rubrique modifiée est repérée comme non enregistrée",
  __t.sectionsNonEnregistrees().length === 1);
confirmCalls = []; confirmReponse = false;
exportCalls = 0; sectionPuts = []; sectionResponder = () => ({});
document.getElementById("expMd").click();
await settle();
check("export avec correction en cours : confirmation demandée, rubrique nommée",
  confirmCalls.length === 1 && confirmCalls[0].includes("Anamnèse"));
check("export refusé : aucun export, aucun enregistrement",
  exportCalls === 0 && sectionPuts.length === 0);
check("export refusé : message explicite",
  document.getElementById("copyStatus").textContent.includes("interrompu"));

confirmReponse = true; confirmCalls = [];
document.getElementById("expMd").click();
await settle();
check("export accepté : la correction est enregistrée puis exportée",
  sectionPuts.length === 1
  && sectionPuts[0].body.contenu.includes("CORRECTION CLINIQUE")
  && exportCalls === 1);

Object.defineProperty(navigator, "clipboard", {
  value: { writeText: async (t) => { copie = t; } }, configurable: true,
});
ecrire("anamnese", "Texte initial. AUTRE CORRECTION");
sectionPuts = []; copie = null;
document.getElementById("copyBilan").click();
await settle();
check("copie : la correction est enregistrée et présente dans le presse-papiers",
  sectionPuts.length === 1 && copie !== null && copie.includes("AUTRE CORRECTION"));

// Le temps de lire la confirmation, le navigateur peut avoir « oublié » le
// clic (activation transitoire) et refuser le presse-papiers : les corrections
// sont bien enregistrées, et le message dit qu'un second clic suffit — pas de
// copier « à la main » (passe réelle du 2026-09-02).
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: async () => { throw new DOMException("refus", "NotAllowedError"); } },
  configurable: true,
});
ecrire("anamnese", "Texte initial. TROISIÈME CORRECTION");
confirmReponse = true; confirmCalls = []; sectionPuts = [];
document.getElementById("copyBilan").click();
await settle();
check("copie refusée après confirmation : la correction est tout de même enregistrée",
  confirmCalls.length === 1 && sectionPuts.length === 1
  && sectionPuts[0].body.contenu.includes("TROISIÈME CORRECTION"));
check("copie refusée après confirmation : invite à cliquer de nouveau, pas à copier à la main",
  document.getElementById("copyStatus").textContent.includes("Cliquez de nouveau")
  && !document.getElementById("copyStatus").textContent.includes("à la main"));
// Sans confirmation intermédiaire, un refus reste un vrai refus.
confirmCalls = [];
document.getElementById("copyBilan").click();
await settle();
check("copie refusée sans confirmation : message « à la main » inchangé",
  confirmCalls.length === 0
  && document.getElementById("copyStatus").textContent.includes("à la main"));
Object.defineProperty(navigator, "clipboard", {
  value: { writeText: async (t) => { copie = t; } }, configurable: true,
});

ecrire("diagnostic", "Diagnostic corrigé à la main");
confirmReponse = false; statutPuts = []; sectionPuts = [];
document.getElementById("valideBtn").click();
await settle();
check("validation refusée : le bilan n'est pas marqué validé",
  statutPuts.length === 0 && sectionPuts.length === 0);
confirmReponse = true;
document.getElementById("valideBtn").click();
await settle();
check("validation acceptée : rubrique enregistrée, puis statut « valide »",
  sectionPuts.length === 1 && statutPuts.length === 1 && statutPuts[0].statut === "valide");

// === 28. Changer de dossier avec du travail en cours (audit 08-11, 2.1) ======
// Une dictée transcrite ne dépend pas du bilan affiché : sans garde-fou, elle
// survivait au changement de dossier et partait dans le suivant.
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
await settle();
document.getElementById("dicteeText").value = "dictée du patient A";
recentsResponder = () => [{ id: 55, statut: "brouillon", domaine_titres: "Générique" }];
await __t.loadRecents();
confirmCalls = []; confirmReponse = false;
document.querySelector('#recents a[data-id="55"]').click();
await settle();
check("changement de dossier avec dictée non analysée : confirmation demandée",
  confirmCalls.length === 1 && confirmCalls[0].includes("autre patient"));
check("refus : on reste sur le dossier courant, la dictée est intacte",
  __t.CUR.id === "b1" && document.getElementById("dicteeText").value === "dictée du patient A");
confirmReponse = true;
document.querySelector('#recents a[data-id="55"]').click();
await settle();
check("acceptation : dossier changé ET dictée effacée (jamais reportée ailleurs)",
  String(__t.CUR.id) === "55" && document.getElementById("dicteeText").value === "");

document.getElementById("dicteeText").value = "dictée résiduelle";
confirmReponse = false; bilanCreates = 0;
document.getElementById("newBilan").click();
await settle();
check("« + Nouveau bilan » avec dictée en cours : refus → aucun bilan créé",
  bilanCreates === 0 && document.getElementById("dicteeText").value === "dictée résiduelle");
document.getElementById("dicteeText").value = "";

// Micro actif : refus net (la transcription arriverait dans le mauvais dossier).
document.getElementById("recBtn").click();
await settle();
confirmCalls = []; bilanCreates = 0;
document.getElementById("newBilan").click();
await settle();
check("enregistrement en cours : changement de dossier refusé sans confirmation",
  bilanCreates === 0 && confirmCalls.length === 0
  && status().includes("Arrêtez d'abord"));
// `#curBilan` porte l'identité du dossier ouvert : un message d'erreur ne doit
// jamais la remplacer (on ne doit pas perdre de vue dans quel dossier on écrit).
check("… et le dossier ouvert reste identifié dans l'en-tête",
  /^#\S+/.test(document.getElementById("curBilan").textContent)
  && !document.getElementById("curBilan").textContent.includes("Arrêtez"));
document.getElementById("recBtn").click();
await settle();
document.getElementById("dicteeText").value = "";

// === 29. La dictée survit à une analyse partielle (audit 08-11, 2.2) =========
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
await settle();
document.getElementById("dicteeText").value = "dictée à ranger";
structureResponder = () => ({
  bilan: structuredClone(CUR0), questions: [], updates_non_placees: ["rubrique_inconnue"],
});
document.getElementById("structBtn").click();
await settle();
check("passage non rangé : le statut invite à relancer l'analyse",
  status().includes("relancez"));
check("passage non rangé : la dictée est conservée (seule copie du texte)",
  document.getElementById("dicteeText").value === "dictée à ranger");
structureResponder = () => ({ bilan: structuredClone(CUR0), questions: [] });
document.getElementById("structBtn").click();
await settle();
check("analyse complète : la dictée est effacée",
  document.getElementById("dicteeText").value === "");

// === 30. Épreuves : saisie bornée, alerte de plausibilité, retrait possible ==
// (audit 08-11, 1.2 et 1.3 : une épreuve était indélébile, et une valeur
// invraisemblable produisait un drapeau sans un mot.)
const epStatus = () => document.getElementById("epStatus").textContent;
const bep = structuredClone(CUR0); bep.id = "bep"; bep.epreuves = [];
__t.CUR = bep;
__t.renderBilan();
await settle();
document.getElementById("epTest").value = "Alouette-R";
epreuvePosts = [];
document.getElementById("epAdd").click();
await settle();
check("épreuve sans score ni étalonnage : refusée avant l'appel serveur",
  epreuvePosts.length === 0 && epStatus().includes("score brut"));

const bepPlein = structuredClone(bep);
bepPlein.epreuves = [{ id: 9, test_nom: "Alouette-R", resultats: [
  { sous_epreuve: "", score_brut: "12", etalonnage_type: "percentile",
    etalonnage_valeur: "-300", drapeau_seuil: "severe" }],
  // Recalculée par le serveur à chaque lecture (passe réelle du 2026-09-02).
  avertissements: ["Alouette-R : « -300 » sort des valeurs possibles "
                   + "(un percentile va de 0 à 100)."] }];
epreuveResponder = (suppression) => suppression
  ? { ...structuredClone(bep), epreuves: [] }
  : { ...structuredClone(bepPlein),
      avertissements: ["Alouette-R : « -300 » sort des valeurs possibles "
                       + "(un percentile va de 0 à 100)."] };
document.getElementById("epScore").value = "12";
document.getElementById("epType").value = "percentile";
document.getElementById("epVal").value = "-300";
document.getElementById("epAdd").click();
await settle();
check("épreuve ajoutée : l'avertissement de plausibilité est affiché",
  epStatus().includes("sort des valeurs possibles"));
check("épreuve ajoutée : les champs de saisie sont vidés",
  document.getElementById("epTest").value === ""
  && document.getElementById("epVal").value === "");
check("épreuve ajoutée : elle apparaît avec son ✕ de retrait",
  document.querySelector("[data-ep-del]") !== null);
check("épreuve : l'alerte de plausibilité est affichée sous l'épreuve, pas seulement dans le statut",
  document.querySelector("#epList .ep-alerte")?.textContent.includes("sort des valeurs possibles") === true);
// Rechargement (F5, verrouillage) : le bilan relu du serveur porte l'alerte,
// elle doit rester visible sans nouvelle saisie.
__t.CUR = structuredClone(bepPlein);
__t.renderBilan();
check("épreuve : l'alerte survit à un re-rendu depuis le bilan relu",
  document.querySelector("#epList .ep-alerte")?.textContent.includes("0 à 100") === true);
__t.CUR = structuredClone(bepPlein); __t.CUR.epreuves[0].avertissements = [];
__t.renderBilan();
check("épreuve plausible : aucune alerte affichée",
  document.querySelector("#epList .ep-alerte") === null);
__t.CUR = bepPlein;
__t.renderBilan();

confirmCalls = []; confirmReponse = false; epreuveDeletes = [];
document.querySelector("[data-ep-del]").click();
await settle();
check("retrait refusé : aucune suppression",
  confirmCalls.length === 1 && epreuveDeletes.length === 0);
confirmReponse = true;
document.querySelector("[data-ep-del]").click();
await settle();
check("retrait confirmé : DELETE envoyé, l'épreuve disparaît de l'écran",
  epreuveDeletes.length === 1 && document.querySelector("[data-ep-del]") === null);

// Une saisie d'épreuve en cours survit à un re-rendu (analyse qui se termine).
document.getElementById("epTest").value = "EXALANG";
document.getElementById("epScore").value = "17";
__t.renderBilan();
await settle();
check("re-rendu : la ligne d'épreuve en cours de saisie est préservée",
  document.getElementById("epTest").value === "EXALANG"
  && document.getElementById("epScore").value === "17");
check("saisieEnCours : une épreuve en cours de saisie compte",
  __t.saisieEnCours() === true);
["epTest", "epSub", "epScore", "epType", "epVal"].forEach((id) => {
  document.getElementById(id).value = "";
});

// === 31. Supprimer un bilan entier (audit 08-11, 1.2) =======================
confirmCalls = []; confirmReponse = false; bilanDeletes = 0;
document.getElementById("delBilan").click();
await settle();
check("suppression du bilan refusée : aucun appel",
  confirmCalls.length === 1 && bilanDeletes === 0);
confirmReponse = true;
document.getElementById("delBilan").click();
await settle();
check("suppression confirmée : DELETE envoyé, écran vidé",
  bilanDeletes === 1 && __t.CUR === null
  && document.getElementById("curBilan").textContent.includes("supprimé"));

// === 32. Ollama absent sur un coffre déjà créé (audit 08-11, 6.1) ===========
// L'écran d'installation enfermait dehors une personne qui voulait seulement
// rouvrir ou exporter un bilan, avec pour seule instruction de réinstaller 1 Go.
statusResponder = () => ({ db_exists: true, unlocked: true, first_run: false, version: "1.8.0" });
installResponder = () => ({ ollama: false, pret: false, config_lisible: false,
                            modeles: [], proposition: { modele: "qwen3.5:4b", raison: "" } });
await __t.gate();
await settle();
check("coffre existant + Ollama absent : l'installation ne bloque pas l'écran",
  document.getElementById("installOverlay").hidden === true);
check("… un bandeau nomme ce qui reste possible (consultation, export)",
  document.getElementById("iaBanner").hidden === false
  && document.getElementById("iaBannerTexte").textContent.includes("export"));
check("… et le geste qui répare, pas une réinstallation",
  document.getElementById("iaBannerTexte").textContent.includes("Lancez Ollama"));
// 6.5 : première visite sur ce poste → l'aide « Comment ça marche » s'est
// ouverte d'elle-même (une seule fois : mémorisé dans localStorage).
check("première visite : l'aide s'ouvre d'elle-même au premier déverrouillage",
  document.getElementById("helpOverlay").hidden === false
  && localStorage.getItem("bilan_ortho_aide_vue") === "1");
document.getElementById("helpOverlay").hidden = true;

// Coffre verrouillé : le serveur lit les défauts, pas la config du praticien —
// aucun « modèle manquant » ne doit être affirmé.
document.getElementById("iaBanner").hidden = true;
statusResponder = () => ({ db_exists: true, unlocked: false, first_run: false, version: "1.8.0" });
installResponder = () => ({ ollama: true, pret: false, config_lisible: false,
                            modeles: ["qwen3.5:4b"], embeddings_present: false,
                            embeddings_configure: "nomic-embed-text",
                            proposition: { modele: "qwen3.5:9b", raison: "" } });
await __t.gate();
await settle();
check("coffre verrouillé : aucun modèle manquant n'est affirmé (config illisible)",
  document.getElementById("iaBanner").hidden === true);
overlay().hidden = true;

// Premier lancement (aucun coffre) : l'écran guidé reste bloquant, à raison.
statusResponder = () => ({ db_exists: false, unlocked: false, first_run: true, version: "1.8.0" });
installResponder = () => ({ ollama: false, pret: false, config_lisible: false,
                            modeles: [], proposition: { modele: "qwen3.5:4b", raison: "" } });
await __t.gate();
await settle();
check("premier lancement : l'écran d'installation reste bloquant",
  document.getElementById("installOverlay").hidden === false);
document.getElementById("installOverlay").hidden = true;

// === 2.4 (revue 2026-08-11) : une analyse en cours peut être annulée ========
// Sans cela, la seule issue pendant les minutes d'attente était F5 — qui
// perdait la dictée. L'annulation ferme la requête ; la dictée reste.
__t.CUR = structuredClone(CUR0); __t.renderBilan();
structureResponder = () => ({ bilan: structuredClone(CUR0), questions: [] });
let libererAnalyse;
holdNext = new Promise((r) => (libererAnalyse = r));
document.getElementById("dicteeText").value = "dictée longue à analyser";
document.getElementById("structBtn").click();
await settle();
const cancelBtn = document.getElementById("structCancel");
check("analyse en cours : « Annuler l'analyse » visible et actif",
  cancelBtn.hidden === false && cancelBtn.disabled === false
  && document.getElementById("structBtn").disabled === true);
cancelBtn.click();
await settle();
check("annulation : statut explicite, dictée conservée",
  status().includes("annulée") && status().includes("conservée")
  && document.getElementById("dicteeText").value === "dictée longue à analyser");
check("annulation : « Structurer » réactivé, « Annuler » masqué",
  document.getElementById("structBtn").disabled === false && cancelBtn.hidden === true);
libererAnalyse(); holdNext = null;
await settle();
check("réponse tardive après annulation : l'écran n'est pas touché",
  status().includes("annulée"));
// Hors analyse, le bouton n'existe pas à l'écran.
holdNext = null;
document.getElementById("structBtn").click();
await settle();
check("analyse suivante menée à terme : « Annuler » disparaît", cancelBtn.hidden === true
  && !status().includes("annulée"));

// Relance juste après « Annuler » : le serveur met quelques secondes à
// constater la fermeture de la requête et à libérer la place (409 « déjà en
// cours » entre-temps, vu en conditions réelles avec Chromium + Ollama). La
// relance doit patienter et réessayer, pas afficher une erreur.
document.getElementById("dicteeText").value = "dictée à relancer";
holdNext = new Promise((r) => (libererAnalyse = r));
document.getElementById("structBtn").click();
await settle();
cancelBtn.click();
await settle();
libererAnalyse(); holdNext = null;
let refus = 2;
const appelsAvant = structureCalls.length;
structureResponder = () => refus-- > 0
  ? { __status: 409, detail: "Une analyse est déjà en cours pour ce bilan." }
  : { bilan: structuredClone(CUR0), questions: [] };
document.getElementById("structBtn").click();
await settle();
check("relance après annulation : le 409 n'est pas montré comme une erreur",
  !status().includes("Erreur") && status().includes("précédente"));
await new Promise((r) => setTimeout(r, 2300));
await settle();
check("relance après annulation : réessayée jusqu'au succès",
  structureCalls.length === appelsAvant + 3 && !status().includes("Erreur")
  && !status().includes("précédente") && document.getElementById("structBtn").disabled === false);

// === 2.5 (revue 2026-08-11) : 🔒 Verrouiller ne laisse rien à l'écran =======
// Le rechargement déclenchait le dialogue natif « quitter le site ? » ; en
// l'annulant, la personne gardait patient, dictée et bilan affichés alors que
// le coffre était verrouillé. La question est posée AVANT, le garde-fou
// s'efface APRÈS.
check("restauration réussie (scénario 20) : le rechargement ne sera pas bloqué par le garde-fou",
  __t.QUITTER_SANS_GARDE === true);
__t.QUITTER_SANS_GARDE = false; // état d'une page fraîchement chargée
let reloads = 0;
Object.defineProperty(window.location, "reload", { value: () => { reloads++; }, configurable: true });
document.getElementById("dicteeText").value = "dictée jamais analysée";
const evAvant = new Event("beforeunload", { cancelable: true });
window.dispatchEvent(evAvant);
check("saisie en cours : quitter la page demande confirmation (garde-fou actif)",
  evAvant.defaultPrevented === true);
confirmCalls = []; confirmReponse = false; lockCalls = 0;
document.getElementById("lockBtn").click();
await settle();
check("verrouiller avec saisie en cours : confirmation demandée, perte annoncée",
  confirmCalls.length === 1 && confirmCalls[0].includes("perdue"));
check("refus : coffre NON verrouillé, page non rechargée, dictée intacte",
  lockCalls === 0 && reloads === 0
  && document.getElementById("dicteeText").value === "dictée jamais analysée");
confirmReponse = true; confirmCalls = [];
document.getElementById("lockBtn").click();
await settle();
check("acceptation : verrouillage demandé PUIS rechargement",
  lockCalls === 1 && reloads === 1);
const evApres = new Event("beforeunload", { cancelable: true });
window.dispatchEvent(evApres);
check("… sans dialogue natif : le garde-fou beforeunload s'est effacé",
  evApres.defaultPrevented === false);

// === 6.4 / 6.5 (revue 2026-08-11) : sélecteur de modèle honnête, domaine choisi
// Le modèle configuré (CFG.llm.model) n'est pas dans la liste renvoyée par
// Ollama : l'écran doit le dire, pas afficher le premier de la liste.
await __t.loadLLM();
const selModele = document.getElementById("llmModel");
// (happy-dom laisse selectedIndex à -1 : on retrouve l'option par sa valeur.)
const optConfig = [...selModele.options].find((o) => o.value === "qwen2.5:7b");
check("modèle configuré non installé : affiché tel quel, marqué « non installé »",
  selModele.value === "qwen2.5:7b" && optConfig && optConfig.textContent.includes("non installé"));
check("… les modèles installés restent proposés",
  [...selModele.options].some((o) => o.value === "qwen3.5:9b"));

// « Générique » n'est plus le défaut silencieux : sans domaine choisi, pas de
// bilan, et le message dit où est le tronc commun.
await __t.loadDomaines();
const selDom = document.getElementById("domaine");
check("domaine : l'invite « Choisissez… » est sélectionnée, Générique en bas de liste",
  selDom.value === "__choisir__"
  && selDom.options[selDom.options.length - 1].textContent.includes("Générique"));
// L'enregistrement lancé au scénario 28 est toujours « en cours » : on
// l'arrête, sinon tout changement de dossier est refusé pour cette raison.
if (document.getElementById("recBtn").classList.contains("rec")) {
  document.getElementById("recBtn").click();
  await settle();
}
document.getElementById("dicteeText").value = "";
__t.CUR = null; bilanCreates = 0;
document.getElementById("newBilan").click();
await settle();
check("« + Nouveau bilan » sans domaine : refusé, message explicite",
  bilanCreates === 0 && status().includes("domaine"));
selDom.value = "langage_oral";
document.getElementById("newBilan").click();
await settle();
check("« + Nouveau bilan » avec un domaine : créé", bilanCreates === 1);

// === 5.2 (revue 2026-08-11) : changer la passphrase depuis Paramètres =======
const ppStatus = () => document.getElementById("ppStatus").textContent;
document.getElementById("ppAncienne").value = "passphrase-de-test";
document.getElementById("ppNouvelle").value = "les hérons volent bas ce soir";
document.getElementById("ppConfirm").value = "les hérons volent bas ce matin";
document.getElementById("ppBtn").click();
await settle();
check("passphrase : confirmation différente → aucun appel, message explicite",
  passphrasePosts.length === 0 && ppStatus().includes("confirmation"));
document.getElementById("ppConfirm").value = "les hérons volent bas ce soir";
document.getElementById("ppBtn").click();
await settle();
check("passphrase : POST avec l'ancienne et la nouvelle",
  passphrasePosts.length === 1
  && passphrasePosts[0].ancienne === "passphrase-de-test"
  && passphrasePosts[0].nouvelle === "les hérons volent bas ce soir");
check("passphrase changée : succès, nouvelle sauvegarde nommée, copies antérieures signalées",
  ppStatus().includes("✓") && ppStatus().includes("20260903-101500") && ppStatus().includes("2 copie"));
check("passphrase changée : les trois champs sont vidés",
  ["ppAncienne", "ppNouvelle", "ppConfirm"].every((id) => document.getElementById(id).value === ""));

// === 6.2 (revue 2026-08-11) : un téléchargement qui échoue n'est plus un cul-de-sac
statusResponder = () => ({ db_exists: false, unlocked: false, first_run: true, version: "1.8.0" });
installResponder = () => ({ ollama: true, pret: false, config_lisible: false, modeles: [],
                            llm_present: false, embeddings_present: false,
                            embeddings_configure: "nomic-embed-text",
                            disque_libre_gio: 3.0, taille_a_telecharger_gio: 5.8,
                            proposition: { modele: "qwen3.5:9b", raison: "RAM 32 Gio" } });
await __t.gate();
await settle();
const instStatut = () => document.getElementById("instPullStatus").textContent;
check("installation : l'espace disque insuffisant est annoncé AVANT le téléchargement",
  document.getElementById("instModeles").textContent.includes("Espace disque")
  && document.getElementById("instModeles").textContent.includes("3 Gio"));
check("installation : « Passer cette étape » est proposé tant que rien n'est prêt",
  document.getElementById("instPasser").hidden === false
  && document.getElementById("instContinuer").disabled === true);
pullPosts = [];
document.getElementById("instPull").click();
await settle(); await settle();
check("téléchargement en échec : message en français, pas le texte brut d'Ollama",
  instStatut().includes("n'existe pas") && !instStatut().includes("manifest"));
check("téléchargement en échec : un autre modèle est proposé, le compact pré-rempli",
  document.getElementById("instAutre").hidden === false
  && document.getElementById("instAutreNom").value === "qwen3.5:4b");
// Le modèle de remplacement se télécharge (progression en Mo), puis l'état
// est revérifié AVEC ce modèle, et « Continuer » s'ouvre.
pullLignes = () => ['{"status":"pulling manifest"}', '{"status":"pulling 8f4c","total":2400000000,"completed":1200000000}', '{"status":"success"}'];
installResponder = () => ({ ollama: true, pret: true, config_lisible: false, modeles: ["qwen3.5:4b", "nomic-embed-text"],
                            llm_present: false, embeddings_present: true, embeddings_configure: "nomic-embed-text",
                            disque_libre_gio: 3.0, taille_a_telecharger_gio: 0,
                            proposition: { modele: "qwen3.5:4b", raison: "modèle choisi à l'installation" } });
let urlInstallation = [];
const fetchOrig = globalThis.fetch;
globalThis.fetch = async (p, o) => { if (String(p).includes("/api/installation") && !String(p).includes("/pull")) urlInstallation.push(String(p)); return fetchOrig(p, o); };
document.getElementById("instAutreBtn").click();
await settle(); await settle();
globalThis.fetch = fetchOrig;
check("autre modèle : téléchargé sous le nom saisi",
  pullPosts.length === 2 && pullPosts[1].modele === "qwen3.5:4b");
check("autre modèle : la revérification passe le modèle choisi au serveur",
  urlInstallation.some((u) => u.includes("modele=qwen3.5%3A4b")));
check("autre modèle installé : « Continuer » s'ouvre, statut terminé",
  document.getElementById("instContinuer").disabled === false && instStatut().includes("terminé"));
// « Passer cette étape » sort de l'écran d'installation vers la création du coffre.
installResponder = () => ({ ollama: false, pret: false, config_lisible: false, modeles: [],
                            proposition: { modele: "qwen3.5:4b", raison: "" } });
document.getElementById("installOverlay").hidden = false;
document.getElementById("instPasser").hidden = false;
document.getElementById("instPasser").click();
await settle();
check("« Passer cette étape » : écran d'installation fermé, création du coffre proposée",
  document.getElementById("installOverlay").hidden === true && overlay().hidden === false);
overlay().hidden = true;

// === 6.3 (revue 2026-08-11) : le modèle de dictée dans l'écran d'installation
let whisperPresent = false, whisperEtat = "inactif";
installResponder = () => ({ ollama: true, pret: false, config_lisible: false,
                            modeles: ["qwen3.5:4b", "nomic-embed-text"], llm_present: true, embeddings_present: true,
                            embeddings_configure: "nomic-embed-text",
                            whisper_modele: "medium", whisper_taille_go: 1.5, whisper_present: whisperPresent,
                            whisper_telechargement: whisperPresent ? "termine" : whisperEtat, whisper_erreur: "",
                            disque_libre_gio: 40, taille_a_telecharger_gio: whisperPresent ? 0 : 1.5,
                            proposition: { modele: "qwen3.5:4b", raison: "" } });
document.getElementById("installOverlay").hidden = false;
await __t.gate();
await settle();
check("installation : le modèle de dictée a son étape, à télécharger AVANT toute dictée",
  document.getElementById("instWhisper").textContent.includes("medium")
  && document.getElementById("instWhisperBtn").disabled === false
  && document.getElementById("instContinuer").disabled === true);
__t.INST_POLL_MS = 5;
whisperEtat = "en_cours";  // ce que le serveur répondra une fois le téléchargement lancé
document.getElementById("instWhisperBtn").click();
await settle();
check("modèle de dictée : téléchargement lancé en arrière-plan, suivi en cours",
  whisperPosts === 1 && document.getElementById("instWhisperStatus").textContent.includes("en cours"));
whisperPresent = true;
await settle(); await settle();
check("modèle de dictée installé : statut ✅, étape marquée présente",
  document.getElementById("instWhisperStatus").textContent.includes("✅")
  && document.getElementById("instWhisper").textContent.includes("présent"));
document.getElementById("installOverlay").hidden = true;

// === 6.3 : un audio dont la transcription échoue n'est pas perdu =============
document.getElementById("dicteeText").value = "";
document.getElementById("recBtn").click();   // démarre
await settle();
transcribeKo = true;
document.getElementById("recBtn").click();   // arrête → transcription en échec
await settle();
const recStatusEl = document.getElementById("recStatus");
check("transcription en échec : l'enregistrement est conservé, un bouton « Réessayer » apparaît",
  recStatusEl.textContent.includes("conservé") && document.getElementById("recRetry") !== null
  && document.getElementById("dicteeText").value === "");
transcribeKo = false;
document.getElementById("recRetry").click();
await settle();
check("réessai : le même enregistrement est transcrit, rien à redicter",
  document.getElementById("dicteeText").value.includes("texte transcrit")
  && document.getElementById("recRetry") === null);

// === 17. Verrouillage : la page s'ouvre sur le verrou et voit l'inactivité ==
// (a) Premier rendu : l'écran de verrouillage est dans le HTML, visible avant
// tout script, bouton inactif tant que l'état du coffre est inconnu — jamais
// l'intérieur de l'application pendant l'initialisation.
check("premier rendu : écran de verrouillage visible avant tout script, bouton inactif",
  /id="lockOverlay"(?![^>]*\bhidden)/.test(markup) && /id="unlockBtn"[^>]*\bdisabled/.test(markup));

// (b) Coffre existant : le déverrouillage n'attend pas la vérification de
// l'installation (Ollama, GPU : plusieurs secondes) — ici elle ne répond jamais.
const installAvant = installResponder;
overlay().hidden = false; document.getElementById("unlockBtn").disabled = true;
statusResponder = () => ({ db_exists: true, unlocked: false, first_run: false, version: "1.8.0" });
installResponder = () => new Promise(() => {});
await __t.gate(); await settle();
check("coffre existant : déverrouillage proposé sans attendre la vérification de l'installation",
  overlay().hidden === false && !document.getElementById("unlockBtn").disabled
  && document.getElementById("lockMsg").textContent.includes("Déverrouillez"));
installResponder = installAvant;

// (c) Coffre ouvert (F5) : l'écran est caché et la surveillance armée.
statusResponder = () => ({ db_exists: true, unlocked: true, first_run: false, version: "1.8.0", verrouillage_dans_s: 900 });
await __t.gate(); await settle();
check("coffre ouvert : l'écran de verrouillage est caché", overlay().hidden === true && __t.appStarted);

// (d) Échéance : la page consulte l'état et affiche le verrou sans qu'on clique.
statusResponder = () => ({ db_exists: true, unlocked: false, first_run: false, version: "1.8.0", verrouillage_dans_s: null });
await __t.verifierVerrou(); await settle();
check("verrouillage d'inactivité : le verrou s'affiche sans attendre un clic",
  overlay().hidden === false && document.getElementById("lockMsg").textContent.includes("inactivité"));

// (e) Écran affiché : plus de consultation ; retour de l'onglet : consultation.
let avant = statusCalls;
await __t.verifierVerrou(); await settle();
check("verrou affiché : la surveillance s'arrête", statusCalls === avant);
overlay().hidden = true;
statusResponder = () => ({ db_exists: true, unlocked: true, first_run: false, version: "1.8.0", verrouillage_dans_s: 30 });
avant = statusCalls;
document.dispatchEvent(new Event("visibilitychange")); await settle();
check("retour de l'onglet : l'état est consulté, coffre ouvert → rien ne change",
  statusCalls === avant + 1 && overlay().hidden === true);
check("prochaine vérification : juste après l'échéance, jamais plus de 60 s",
  __t.delaiProchaineVerifS({ verrouillage_dans_s: 30 }) === 31
  && __t.delaiProchaineVerifS({ verrouillage_dans_s: 900 }) === 60
  && __t.delaiProchaineVerifS({ verrouillage_dans_s: null }) === 60
  && __t.delaiProchaineVerifS({ verrouillage_dans_s: 0 }) === 1);

// (f) Activité : une frappe signale l'activité au serveur, au plus une fois
// par minute — et jamais depuis l'écran de verrouillage.
__t.dernierSignalActivite = 0;
let ka = keepaliveCalls;
document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "a", bubbles: true })); await settle();
document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "b", bubbles: true })); await settle();
check("frappe au clavier : un seul keepalive par minute", keepaliveCalls === ka + 1);
__t.dernierSignalActivite = 0; ka = keepaliveCalls;
overlay().hidden = false;
document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "c", bubbles: true })); await settle();
check("depuis l'écran de verrouillage : aucune activité signalée", keepaliveCalls === ka);
overlay().hidden = true;

// === 18. Dossier patient : la remise de la mention d'information est tracée ==
// (RGPD art. 13 ; table `consentement`, type « information »). La case envoie
// `informe` au serveur, la liste montre la date renvoyée, le formulaire de
// modification la reflète.
const patientPosts = [];
let PATIENTS_STUB = [];
const fetchAvantPatients = globalThis.fetch;
globalThis.fetch = async (p, o = {}) => {
  const url = String(p);
  if (url.endsWith("/api/patients") && o.method === "POST") {
    const b = JSON.parse(o.body); patientPosts.push(b);
    const cree = { id: 7, nom: b.nom, prenom: b.prenom, date_naissance: b.date_naissance, sexe: b.sexe,
                   notes: b.notes, nb_bilans: 0, nb_references: 0, informe_le: b.informe ? "2026-09-04" : null };
    PATIENTS_STUB = [cree];
    return rep(cree);
  }
  if (url.endsWith("/api/patients")) return rep(PATIENTS_STUB.map((x) => ({ ...x })));
  return fetchAvantPatients(p, o);
};
const elt = (id) => document.getElementById(id);
elt("patientsBtn").click(); await settle();
check("dossier patient : case « mention d'information remise » présente, décochée par défaut",
  elt("patInforme") !== null && elt("patInforme").checked === false && elt("patientsOverlay").hidden === false);
elt("patNom").value = "Durand"; elt("patInforme").checked = true;
elt("patSave").click(); await settle(); await settle();
check("enregistrement : la remise est envoyée au serveur avec le dossier",
  patientPosts.length === 1 && patientPosts[0].informe === true && patientPosts[0].nom === "Durand");
check("liste des patients : date de remise en clair",
  elt("patList").textContent.includes("information remise le 04/09/2026"));
check("formulaire remis à zéro après enregistrement : case décochée", elt("patInforme").checked === false);
elt("patList").querySelector("a[data-id]").click(); await settle();
check("modification d'un dossier : la case reflète la trace enregistrée", elt("patInforme").checked === true);
globalThis.fetch = fetchAvantPatients;

console.log(failures ? `\n${failures} échec(s)` : "\nTous les scénarios passent.");
process.exit(failures ? 1 : 0);

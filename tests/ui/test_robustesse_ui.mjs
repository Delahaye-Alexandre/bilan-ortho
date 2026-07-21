// Test fonctionnel de la robustesse frontend (audit 2026-07-17, Lot 1) :
// - C2 : les rubriques modifiées non enregistrées survivent au re-rendu
// - C4 : réponse 423 → overlay de verrouillage ré-affiché, pas de crash
// - erreurs réseau traduites en français (wrapper api)
// - anti double-clic (newBilan) et analyse unique (STRUCTURING)
// - réponse tardive après changement de bilan : l'écran n'est pas écrasé
// Lancer : bun tests/ui/test_robustesse_ui.mjs
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register();

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
  start() {}
  stop() {
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

const rep = (r) => r && r.__status
  ? { ok: false, status: r.__status, statusText: "ERR", json: async () => ({ detail: r.detail }) }
  : { ok: true, status: 200, json: async () => r };

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
  if (url.includes("/structure")) {
    structureCalls.push(JSON.parse(o.body));
    if (holdNext) await holdNext;
    return rep(structureResponder());
  }
  if (url.endsWith("/api/bilans") && o.method === "POST") {
    bilanCreates++;
    if (holdNext) await holdNext;
    return rep(bilanCreator());
  }
  if (url.includes("/api/bilans?limit")) {
    return rep([{ id: 7, statut: "brouillon", domaine_titres: "Générique" }]);
  }
  if (url.includes("/sections/")) {
    sectionPuts.push({ url, body: JSON.parse(o.body) });
    return rep(sectionResponder());
  }
  if (url.includes("/api/config/overrides")) return rep(structuredClone(OVERRIDES));
  if (url.includes("/api/config")) return rep(structuredClone(CFG));
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
  renderQuestions, renderBilan, structure, saisieEnCours, loadRecents,
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
const savest = (cle) => document.querySelector(`#bilanView .sec[data-cle="${cle}"] .savest`);
const status = () => document.getElementById("structStatus").textContent;
const overlay = () => document.getElementById("lockOverlay");

// === 1. C2 : une rubrique modifiée non enregistrée survit au re-rendu ========
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
check("rendu initial : contenu serveur affiché", secTa("anamnese").value === "Texte initial.");

secTa("anamnese").value = "Texte initial. CORRIGÉ À LA MAIN";
structureResponder = () => {
  const b = structuredClone(CUR0);
  b.sections[0].contenu = "Texte initial.\n\nAjout proposé par l'IA.";
  return { bilan: b, questions: [] };
};
document.getElementById("dicteeText").value = "une dictée";
document.getElementById("structBtn").click();
await settle();
check("C2 : la correction manuelle non enregistrée est préservée après structuration",
  secTa("anamnese").value === "Texte initial. CORRIGÉ À LA MAIN");
check("C2 : l'utilisateur est prévenu (« non enregistrées »)",
  savest("anamnese").textContent.includes("non enregistrées"));
check("C2 : les rubriques non modifiées suivent le serveur",
  secTa("diagnostic").value === "");

// Après « Enregistrer », le brouillon devient la référence : plus d'alerte.
document.querySelector('#bilanView .sec[data-cle="anamnese"] .save').click();
await settle();
check("C2 : enregistrement du brouillon → PUT envoyé + statut ✓",
  sectionPuts.length === 1 && savest("anamnese").textContent === "✓");
__t.renderBilan();
await settle();
check("C2 : après enregistrement, re-rendu sans alerte ni perte",
  secTa("anamnese").value === "Texte initial. CORRIGÉ À LA MAIN"
  && !savest("anamnese").textContent.includes("non enregistrées"));

// === 2. Les brouillons ne fuient pas vers un autre bilan =====================
secTa("anamnese").value = "BROUILLON DU BILAN 1";
const b2 = structuredClone(CUR0); b2.id = "b2"; b2.sections[0].contenu = "Contenu du bilan 2.";
__t.CUR = b2;
__t.renderBilan();
check("changement de bilan : aucun brouillon de l'ancien bilan n'apparaît",
  secTa("anamnese").value === "Contenu du bilan 2.");

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
  __t.CUR.id === "b9" && secTa("anamnese").value === "Bilan 9.");
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
secTa("anamnese").value = "modif non enregistrée";
check("saisieEnCours : rubrique modifiée non enregistrée → true", __t.saisieEnCours() === true);

// === 9. Éditeur Avancé : surcharges seules, jamais les défauts ===============
document.getElementById("settingsBtn").click();
await settle();
check("modale Paramètres ouverte", document.getElementById("settingsOverlay").hidden === false);
const adv = document.getElementById("cfgAdvanced").value;
check("Avancé : la surcharge du praticien est affichée", adv.includes("MON PROMPT PERSO"));
check("Avancé : les défauts (trame…) ne sont PAS figés dans l'éditeur",
  !adv.includes("Anamnèse") && !adv.includes("trame"));
check("modale : focus posé à l'ouverture",
  document.activeElement === document.getElementById("cfgLlmModel"));

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
__t.CUR = structuredClone(CUR0);
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
  secTa("anamnese") !== null && secTa("anamnese").value === "Texte initial.");

console.log(failures ? `\n${failures} échec(s)` : "\nTous les scénarios passent.");
process.exit(failures ? 1 : 0);

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
let recentsRequests = [];
let recentsResponder = () => [{ id: 7, statut: "brouillon", domaine_titres: "Générique" }];
let exportResponder = null;
let restaurationCalls = [];
let restaurationResponder = () => ({ ok: true, fichier: "f", filet: "g" });
let editeurCalls = [];       // PUT/DELETE des routes /api/config/{trame,catalogues,prompts}
let editeurResponder = null; // null = succès (config effective renvoyée)
const SAUVEGARDES = {
  dossier: "", derniere: "2026-07-20 10:00:00",
  fichiers: [{ fichier: "bilan-ortho-sauvegarde-20260720-100000.db", octets: 4096 }],
};

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
  // AVANT la branche « /structure » : l'URL de la consigne intégrée la contient
  if (url.includes("/api/prompts/structure-defaut"))
    return rep({ prompt: 'CONSIGNE INTÉGRÉE {cles} — réponds {"updates":[]}' });
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
  if (url.includes("/export")) return rep(exportResponder ? exportResponder() : {});
  if (url.includes("/api/bilans?")) {
    const q = Object.fromEntries(url.split("?")[1].split("&").map((kv) => kv.split("=")));
    recentsRequests.push({ limit: +q.limit, offset: +q.offset });
    return rep(recentsResponder(+q.limit, +q.offset));
  }
  if (url.includes("/sections/")) {
    sectionPuts.push({ url, body: JSON.parse(o.body) });
    return rep(sectionResponder());
  }
  const mEd = url.match(/\/api\/config\/(trame|catalogues|prompts)/);
  if (mEd) {
    editeurCalls.push({ cible: mEd[1], method: o.method, body: o.body ? JSON.parse(o.body) : null });
    return rep(editeurResponder ? editeurResponder() : structuredClone(CFG));
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
const focusables = [...modal.querySelectorAll("button, input, select, textarea, a[href]")]
  .filter((el) => !el.disabled && !el.hidden);
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

console.log(failures ? `\n${failures} échec(s)` : "\nTous les scénarios passent.");
process.exit(failures ? 1 : 0);

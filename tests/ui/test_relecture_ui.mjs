// Relecture frontend (2026-09) : chaque scénario ci-dessous échoue sur la
// version d'avant correctif. Ils portent des garanties que l'application tient
// devant un dossier patient, pas des détails d'affichage :
// - les signalements « à vérifier » survivent à un F5 / verrouillage
// - l'effacement d'un patient ne laisse pas sa dictée à l'écran
// - une dictée n'est jamais détruite pour un changement de dossier qui échoue
// - l'en-tête (date, prescripteur) part bien dans le document exporté
// - un modèle d'IA manquant est annoncé après le déverrouillage
// - le patient d'origine d'un import ne « colle » pas à l'import suivant
// - l'identité du dossier ouvert n'est pas remplacée par un message d'erreur
// - le drapeau d'un résultat est échappé comme ses voisins
// Lancer : bun tests/ui/test_relecture_ui.mjs
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register();

const HTML_PATH = new URL("../../app/static/index.html", import.meta.url).pathname;
const html = await Bun.file(HTML_PATH).text();
const scriptStart = html.indexOf("<script>");
const scriptEnd = html.indexOf("</script>");
const scriptBody = html.slice(scriptStart + "<script>".length, scriptEnd);
document.documentElement.innerHTML =
  html.slice(0, scriptStart) + html.slice(scriptEnd + "</script>".length);

// --- Stub micro --------------------------------------------------------------
class FakeMediaRecorder {
  constructor(stream) { this.stream = stream; }
  start() {}
  stop() { this.onstop && this.onstop(); }
}
globalThis.MediaRecorder = FakeMediaRecorder;
const fakeStream = { getTracks: () => [{ stop() {} }] };
try {
  Object.defineProperty(navigator, "mediaDevices", {
    value: { getUserMedia: async () => fakeStream }, configurable: true,
  });
} catch { navigator.mediaDevices = { getUserMedia: async () => fakeStream }; }
try {
  Object.defineProperty(navigator, "clipboard", {
    value: { writeText: async (t) => { globalThis.__copie = t; } }, configurable: true,
  });
} catch {}
globalThis.URL.createObjectURL = () => "blob:test";
globalThis.URL.revokeObjectURL = () => {};

// --- Confirmations pilotées --------------------------------------------------
let confirmCalls = [], confirmReponse = true;
globalThis.confirm = (m) => { confirmCalls.push(m); return confirmReponse; };
window.confirm = globalThis.confirm;

// --- Stub réseau -------------------------------------------------------------
const rep = (r) => r && r.__status
  ? { ok: false, status: r.__status, statusText: "ERR", json: async () => ({ detail: r.detail }) }
  : { ok: true, status: 200, json: async () => r, blob: async () => new Blob(["x"]) };

const CFG = { llm: { model: "qwen2.5:7b" }, maj: { verification_auto: false } };
let statusResponder = () => ({ db_exists: true, unlocked: true, first_run: false, version: "1.8.0" });
let installResponder = () => ({ ollama: true, pret: true, config_lisible: true, modeles: [] });
let patients = [];
let patientDeletes = 0;
let refPosts = [];
let bilanGetKo = false, bilanCreateKo = false;
let bilanCreates = 0, exportCalls = 0;
let entetePuts = [], sectionPuts = [], statutPuts = [];
let CUR0;

globalThis.fetch = async (p, o = {}) => {
  const url = String(p);
  if (url.includes("/api/status")) return rep(statusResponder());
  if (url.includes("/api/installation")) return rep(installResponder());
  if (url.includes("/api/maj")) return rep({ disponible: false });
  if (url.match(/\/api\/patients\/\d+$/) && o.method === "DELETE") {
    patientDeletes++; patients = []; return rep({ ok: true });
  }
  if (url.includes("/api/patients")) return rep(patients.map((x) => ({ ...x })));
  if (url.includes("/api/references")) {
    if (o.method === "POST") {
      const recu = {};
      for (const [k, v] of o.body.entries()) recu[k] = typeof v === "string" ? v : "(fichier)";
      refPosts.push(recu);
      return rep({ n: 3, elements_caviardes: 2, extraits_ecartes: 1 });
    }
    return rep([]);
  }
  if (url.includes("/api/models")) return rep({ models: ["qwen2.5:7b"], default: "qwen2.5:7b" });
  if (url.includes("/api/config")) return rep(structuredClone(CFG));
  if (url.includes("/api/domaines")) return rep([{ cle: "langage_oral", titre: "Langage oral" }]);
  if (url.includes("/api/stt/info")) return rep({ model: "small", device: "cpu" });
  if (url.includes("/api/catalogues/")) return rep({ tests: [] });
  if (url.includes("/api/bilans?")) return rep([]);
  if (url.includes("/export")) { exportCalls++; return rep({}); }
  if (url.includes("/statut")) {
    statutPuts.push(JSON.parse(o.body));
    return rep({ ...structuredClone(CUR0), statut: "valide" });
  }
  if (url.includes("/sections/")) { sectionPuts.push(JSON.parse(o.body)); return rep({ ok: true }); }
  if (url.endsWith("/api/bilans") && o.method === "POST") {
    bilanCreates++;
    if (bilanCreateKo) return rep({ __status: 500, detail: "création impossible" });
    const b = structuredClone(CUR0); b.id = "neuf"; return rep(b);
  }
  const mBil = url.match(/\/api\/bilans\/([\w-]+)$/);
  if (mBil && o.method === "PUT") {
    entetePuts.push(JSON.parse(o.body));
    return rep({ ...structuredClone(CUR0), date_bilan: "2026-09-15",
                 prescripteur: { nom: "MARTIN", rpps: "" } });
  }
  if (mBil && (!o.method || o.method === "GET")) {
    if (bilanGetKo) return rep({ __status: 500, detail: "lecture impossible" });
    const b = structuredClone(CUR0); b.id = mBil[1]; return rep(b);
  }
  return rep({});
};

// --- Évaluation du script de la page (sans le gate() de démarrage) -----------
const body = scriptBody.replace(/gate\(\);\s*$/, "") + `
;globalThis.__t = {
  get CUR() { return CUR; }, set CUR(v) { CUR = v; },
  set appStarted(v) { appStarted = v; },
  renderBilan, renderQuestions, loadBilan, loadPatients, gate, startApp,
  saisieEnCours, enteteModifie,
};`;
new Function(body)();

CUR0 = {
  id: "b1", statut: "brouillon", domaines: [], epreuves: [], patient: null,
  patient_id: 3, date_bilan: "2026-09-01", prescripteur: { nom: "Bernard", rpps: "123" },
  sections: [
    { cle: "anamnese", titre: "Anamnèse", statut: "propose_ia",
      contenu: "Score de 42 à l'Alouette.", signalements: [] },
    { cle: "diagnostic", titre: "Diagnostic", statut: "vide", contenu: "", signalements: [] },
  ],
};

const settle = () => new Promise((r) => setTimeout(r, 30));
let failures = 0;
const check = (label, cond) => {
  console.log(`${cond ? "OK   " : "ECHEC"} ${label}`);
  if (!cond) failures++;
};
const dictee = () => document.getElementById("dicteeText");
const statut = () => document.getElementById("structStatus").textContent;
const verifBloc = (cle) =>
  document.querySelector(`#bilanView .sec[data-cle="${cle}"] .verif`);
const verifTexte = (cle) => (verifBloc(cle) || { textContent: "" }).textContent;

// === 1. Les signalements « à vérifier » survivent au rechargement ============
// Ils portent la promesse centrale du produit (« aucun chiffre inventé ») et le
// coffre les conserve avec la rubrique : un F5, un verrouillage d'inactivité ou
// une relecture le lendemain ne doivent pas les faire disparaître de l'écran
// même où l'on revient relire et valider.
const bSignale = structuredClone(CUR0);
bSignale.sections[0].signalements = ["chiffres absents de votre dictée : 42"];
__t.CUR = bSignale;
__t.renderBilan();
await settle();
check("rubrique rouverte : l'avertissement conservé par le coffre est réaffiché",
  !!verifBloc("anamnese"));
check("… avec le détail de ce qui n'a pas été retrouvé",
  verifTexte("anamnese").includes("42"));
check("… et rien n'est signalé sur les rubriques sans signalement",
  verifBloc("diagnostic") === null);

// Enregistrer la rubrique, c'est l'avoir relue : l'avertissement doit partir et
// ne pas ressusciter au re-rendu suivant (le serveur l'efface aussi).
sectionPuts = [];
document.querySelector('#bilanView .sec[data-cle="anamnese"] .save').click();
await settle();
check("rubrique enregistrée : l'avertissement disparaît", !verifBloc("anamnese"));
__t.renderBilan();
await settle();
check("… et ne revient pas au re-rendu suivant", !verifBloc("anamnese"));

// === 2. Effacer un patient n'abandonne pas sa dictée à l'écran ===============
// Sans cela, la dictée du dossier effacé partait telle quelle dans le bilan du
// patient suivant : la pire issue possible pour cet outil.
patients = [{ id: 3, nom: "Durand", prenom: "Léa", nb_bilans: 2, nb_references: 1 }];
await __t.loadPatients();
await settle();
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
await settle();
dictee().value = "Contenu clinique dicté pour ce dossier.";
confirmCalls = []; confirmReponse = true; patientDeletes = 0;
document.querySelector("#patList .delpat").click();
await settle();
check("effacement du patient : la suppression est bien demandée", patientDeletes === 1);
check("effacement du patient : sa dictée ne reste pas à l'écran", dictee().value === "");
check("effacement du patient : plus aucun dossier ouvert", __t.CUR === null);

// === 3. La dictée n'est détruite qu'une fois le dossier réellement changé ====
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
await settle();
dictee().value = "DICTÉE CLINIQUE IMPORTANTE";
confirmCalls = []; confirmReponse = true; bilanGetKo = true;
await __t.loadBilan("b2");
await settle();
bilanGetKo = false;
check("changement de dossier confirmé mais en échec : on reste sur le dossier",
  __t.CUR.id === "b1");
check("… et la dictée n'a PAS été détruite au passage",
  dictee().value === "DICTÉE CLINIQUE IMPORTANTE");
check("… l'échec est dit dans la zone de statut", statut().includes("Erreur"));

// Création de bilan qui échoue : même exigence.
bilanCreateKo = true; bilanCreates = 0; confirmCalls = [];
document.getElementById("newBilan").click();
await settle();
bilanCreateKo = false;
check("création de bilan en échec : la dictée est conservée",
  dictee().value === "DICTÉE CLINIQUE IMPORTANTE");

// Changement réussi : là, et seulement là, la dictée abandonnée disparaît.
confirmCalls = [];
await __t.loadBilan("b2");
await settle();
check("changement de dossier réussi : le dossier a changé", __t.CUR.id === "b2");
check("… et la dictée abandonnée ne suit pas dans le nouveau dossier",
  dictee().value === "");

// === 4. L'en-tête non enregistré ne part pas en silence ======================
// Date du bilan et prescripteur sont deux mentions obligatoires reprises sur
// l'export : saisies mais pas enregistrées, le document partait sans elles.
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
await settle();
document.getElementById("entPresc").value = "MARTIN";
check("en-tête modifié : la saisie est détectée", __t.enteteModifie() === true);

confirmCalls = []; confirmReponse = false; exportCalls = 0; entetePuts = [];
document.getElementById("expMd").click();
await settle();
check("export avec en-tête non enregistré : confirmation demandée",
  confirmCalls.length === 1 && confirmCalls[0].includes("en-tête"));
check("export refusé : rien n'est exporté ni enregistré",
  exportCalls === 0 && entetePuts.length === 0);

confirmReponse = true; confirmCalls = [];
document.getElementById("expMd").click();
await settle();
check("export accepté : l'en-tête est enregistré PUIS le document exporté",
  entetePuts.length === 1 && entetePuts[0].prescripteur === "MARTIN" && exportCalls === 1);
check("… et l'en-tête n'est plus signalé comme modifié", __t.enteteModifie() === false);

// Même exigence pour « Marquer validé » : on ne valide pas une version qu'on
// n'a pas sous les yeux.
document.getElementById("entPresc").value = "DUPONT";
confirmCalls = []; confirmReponse = false; statutPuts = [];
document.getElementById("valideBtn").click();
await settle();
check("validation avec en-tête non enregistré : confirmation demandée puis refus tenu",
  confirmCalls.length === 1 && statutPuts.length === 0);

// === 5. Un modèle manquant est annoncé après le déverrouillage ===============
// Au chargement de la page le coffre est verrouillé : le serveur lit les
// défauts et ne peut affirmer aucun modèle manquant. Sans second passage,
// l'absence n'était découverte qu'au premier « Structurer ».
document.getElementById("iaBanner").hidden = true;
statusResponder = () => ({ db_exists: true, unlocked: false, first_run: false, version: "1.8.0" });
installResponder = () => ({ ollama: true, pret: false, config_lisible: false,
                            modeles: [], llm_present: false, embeddings_present: false,
                            embeddings_configure: "nomic-embed-text",
                            proposition: { modele: "qwen2.5:7b", raison: "" } });
await __t.gate();
await settle();
check("coffre verrouillé : rien n'est affirmé sur les modèles",
  document.getElementById("iaBanner").hidden === true);
document.getElementById("lockOverlay").hidden = true;

// Déverrouillage : c'est exactement ce que fait doUnlock().
installResponder = () => ({ ollama: true, pret: false, config_lisible: true,
                            modeles: [], llm_present: false, embeddings_present: false,
                            embeddings_configure: "nomic-embed-text",
                            proposition: { modele: "qwen2.5:7b", raison: "" } });
__t.appStarted = false;
await __t.startApp();
await settle();
check("après déverrouillage : le modèle manquant est enfin annoncé",
  document.getElementById("iaBanner").hidden === false);
check("… en nommant les modèles à télécharger",
  document.getElementById("iaBannerTexte").textContent.includes("nomic-embed-text"));

// === 10. « Revérifier » ne masque que ce qui est réparé ======================
installResponder = () => ({ ollama: true, pret: false, config_lisible: false,
                            modeles: [], proposition: { modele: "qwen2.5:7b", raison: "" } });
document.getElementById("iaBannerRevoir").click();
await settle();
check("revérification sans réparation : l'avertissement reste affiché",
  document.getElementById("iaBanner").hidden === false);
installResponder = () => ({ ollama: true, pret: true, config_lisible: true, modeles: [] });
document.getElementById("iaBannerRevoir").click();
await settle();
check("revérification après réparation : l'avertissement disparaît",
  document.getElementById("iaBanner").hidden === true);

// === 6. Le patient d'origine ne colle pas à l'import suivant =================
// Conservé, il rattachait silencieusement le document suivant — souvent un
// bilan externe — au patient précédent, qui l'emporterait à son effacement.
patients = [{ id: 3, nom: "Durand", prenom: "Léa", nb_bilans: 1, nb_references: 0 }];
await __t.loadPatients();
await settle();
const refSel = document.getElementById("refPatient");
check("la liste des patients alimente « Patient d'origine »",
  [...refSel.options].some((o) => o.value === "3"));
refSel.value = "3";
const refFile = document.getElementById("refFile");
Object.defineProperty(refFile, "files", {
  value: [new File(["contenu"], "bilan.txt")], configurable: true,
});
refPosts = [];
document.getElementById("refImport").click();
await settle();
check("import : le patient d'origine est transmis au serveur",
  refPosts.length === 1 && refPosts[0].patient_id === "3");
check("import : le compte rendu du caviardage est affiché",
  document.getElementById("refStatus").textContent.includes("masqué"));
check("import : « Patient d'origine » est remis à zéro pour l'import suivant",
  refSel.value === "");

// === 7. L'identité du dossier ouvert n'est jamais remplacée par une erreur ===
// Remplacer « #b7 · DURAND Léa · … » par « Erreur : … » fait perdre de vue dans
// quel dossier on écrit — le pire endroit où loger un message d'erreur.
const bSept = structuredClone(CUR0); bSept.id = "b7";
__t.CUR = bSept;
__t.renderBilan();
await settle();
dictee().value = "";
document.getElementById("structStatus").textContent = "";
confirmCalls = []; confirmReponse = true;
const labelAvant = document.getElementById("curBilan").textContent;
bilanGetKo = true;
await __t.loadBilan("b8");
await settle();
bilanGetKo = false;
check("échec de chargement : aucune confirmation parasite (rien en cours)",
  confirmCalls.length === 0);
check("échec de chargement : le dossier ouvert reste identifié dans l'en-tête",
  document.getElementById("curBilan").textContent === labelAvant);
check("… et l'erreur est lisible dans la zone de statut", statut().includes("Erreur"));

// === 8. Le drapeau d'un résultat est échappé comme ses voisins ===============
// `drapeau_seuil` est accepté tel quel par l'API : interpolé brut, un contenu
// balisé devenait un élément vivant du compte-rendu.
const bPiege = structuredClone(CUR0);
bPiege.epreuves = [{ id: 5, test_nom: "Alouette-R", resultats: [{
  sous_epreuve: "lecture", score_brut: "42", etalonnage_type: "ecart_type",
  etalonnage_valeur: "-1,5", drapeau_seuil: 'pathologique<img src=x onerror="globalThis.__XSS=1">',
}] }];
__t.CUR = bPiege;
__t.renderBilan();
await settle();
const epList = document.getElementById("epList");
check("drapeau balisé : aucun élément n'est créé à partir du contenu",
  epList.querySelector("img") === null && !globalThis.__XSS);
check("drapeau balisé : le texte est affiché littéralement",
  epList.textContent.includes("<img"));
check("la ligne d'épreuve reste retirable (✕ présent)",
  !!epList.querySelector('[data-ep-del="5"]'));

console.log(failures ? `\n${failures} scénario(s) en échec.` : "\nTous les scénarios passent.");
if (failures) process.exit(1);

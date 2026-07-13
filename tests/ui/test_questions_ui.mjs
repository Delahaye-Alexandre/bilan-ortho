// Test fonctionnel du panneau « Questions de l'assistant » :
// bug réponses perdues + améliorations (micro par question, écarter, chrono)
// + payload structuré avec mémoire du dialogue (réponses, en attente, répondues, écartées).
// Charge la vraie page dans happy-dom, stubbe fetch/MediaRecorder, rejoue les parcours.
// Lancer : bun tests/ui/test_questions_ui.mjs   (bun installe happy-dom à la volée)
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
let holdNext = null; // promesse pour tester l'état « en vol » / le chrono

globalThis.fetch = async (p, o = {}) => {
  if (String(p).includes("/structure")) {
    const payload = JSON.parse(o.body);
    structureCalls.push(payload);
    if (holdNext) await holdNext;
    const r = structureResponder(payload);
    if (r.__status) {
      return { ok: false, status: r.__status, statusText: "ERR", json: async () => ({ detail: r.detail }) };
    }
    return { ok: true, json: async () => r };
  }
  if (String(p).includes("/transcribe")) {
    return { ok: true, json: async () => ({ text: "sept ans et demi" }) };
  }
  return { ok: true, json: async () => ({}) };
};

// --- Évaluation du script de la page (sans le gate() de démarrage) -----------
const body = scriptBody.replace(/gate\(\);\s*$/, "") + `
;globalThis.__t = {
  get QS() { return QS; }, set QS(v) { QS = v; },
  get CUR() { return CUR; }, set CUR(v) { CUR = v; },
  get ansRec() { return ansRec; },
  get DISMISSED() { return DISMISSED; },
  renderQuestions, structure,
};`;
new Function(body)();

const CUR0 = {
  id: "b1", statut: "brouillon", domaines: [], epreuves: [],
  sections: [{ cle: "anamnese", titre: "Anamnèse", statut: "vide", contenu: "" }],
};
__t.CUR = structuredClone(CUR0);

const settle = () => new Promise((r) => setTimeout(r, 25));
let failures = 0;
const check = (label, cond) => {
  console.log(`${cond ? "OK   " : "ECHEC"} ${label}`);
  if (!cond) failures++;
};
const cards = () => [...document.querySelectorAll("#questions .q")];
const inputs = () => cards().map((c) => c.querySelector(".ans"));
const ansBtns = () => cards().map((c) => c.querySelector(".ansBtn"));
const micBtns = () => cards().map((c) => c.querySelector(".qMic"));
const dropBtns = () => cards().map((c) => c.querySelector(".qDrop"));
const qTexts = () => cards().map((c) => c.querySelector("b").textContent);
const status = () => document.getElementById("structStatus").textContent;

// === Round 1 : dictée initiale → 3 questions =================================
structureResponder = () => ({
  bilan: structuredClone(CUR0),
  questions: [
    { section: "", question: "Quel âge a le patient ?", pourquoi: "étalonnage" },
    { section: "", question: "Le score ELO est-il en note standard ?", pourquoi: "" },
    { section: "", question: "Y a-t-il un suivi ORL ?", pourquoi: "" },
  ],
});
document.getElementById("dicteeText").value = "dictée initiale";
document.getElementById("structBtn").click();
await settle();
check("3 questions affichées après la dictée", cards().length === 3);
check("dictée envoyée en transcription pure (aucune réponse)",
  structureCalls[0].transcription === "dictée initiale" && structureCalls[0].reponses.length === 0);
check("bouton groupé caché (aucune réponse saisie)",
  document.getElementById("qAllRow").style.display === "none");

// Brouillons dans Q1 et Q2
inputs()[0].value = "7 ans";
inputs()[0].dispatchEvent(new Event("input"));
inputs()[1].value = "oui, note standard";
inputs()[1].dispatchEvent(new Event("input"));
check("bouton groupé visible avec 2 réponses saisies",
  document.getElementById("qAllRow").style.display !== "none"
  && document.getElementById("qSendAll").textContent === "Envoyer les 2 réponses");

// === Round 2 : répondre à Q3 seule ; l'IA repose Q1 (dupli) + 1 nouvelle =====
inputs()[2].value = "non, RAS";
structureResponder = () => ({
  bilan: structuredClone(CUR0),
  questions: [
    { section: "", question: "Quel âge a le patient ?", pourquoi: "" },
    { section: "", question: "Une plainte attentionnelle est-elle rapportée ?", pourquoi: "" },
  ],
});
holdNext = new Promise((r) => setTimeout(r, 60));
ansBtns()[2].click();
await new Promise((r) => setTimeout(r, 20));
check("pendant l'analyse : boutons Répondre/✕/micro désactivés",
  ansBtns().every((b) => b.disabled) && dropBtns().every((b) => b.disabled)
  && micBtns().every((b) => b.disabled) && document.getElementById("qSendAll").disabled);
check("pendant l'analyse : champs toujours éditables", !inputs()[0].disabled);
holdNext = null;
await new Promise((r) => setTimeout(r, 80));

check("la question répondue (ORL) est retirée — et elle seule",
  cards().length === 3 && !qTexts().some((t) => t.includes("ORL")));
check("brouillon Q1 préservé après re-rendu", inputs()[0].value === "7 ans");
check("brouillon Q2 préservé après re-rendu", inputs()[1].value === "oui, note standard");
check("question reposée par l'IA dédoublonnée (1 seule carte « âge »)",
  qTexts().filter((t) => t.includes("âge")).length === 1);
check("nouvelle question ajoutée en fin de liste", qTexts()[2].includes("attentionnelle"));
check("réponse envoyée structurée AVEC sa question (routage contextualisé)",
  structureCalls[1].transcription === "" && structureCalls[1].reponses.length === 1
  && structureCalls[1].reponses[0].question === "Y a-t-il un suivi ORL ?"
  && structureCalls[1].reponses[0].reponse === "non, RAS");
check("les questions encore affichées sont envoyées « en attente »",
  structureCalls[1].questions_en_attente.length === 2
  && structureCalls[1].questions_en_attente.includes("Quel âge a le patient ?"));
check("boutons ré-activés après l'analyse", ansBtns().every((b) => !b.disabled));

// === Round 3 : envoi groupé des 2 réponses restantes =========================
structureResponder = () => ({ bilan: structuredClone(CUR0), questions: [] });
document.getElementById("qSendAll").click();
await settle();
check("envoi groupé : les 2 paires question/réponse dans UN SEUL appel",
  structureCalls[2].reponses.length === 2
  && structureCalls[2].reponses.some((r) => r.question === "Quel âge a le patient ?" && r.reponse === "7 ans")
  && structureCalls[2].reponses.some((r) => r.question.includes("note standard ?") && r.reponse === "oui, note standard"));
check("la question répondue au tour précédent est envoyée « déjà répondue »",
  structureCalls[2].questions_repondues.includes("Y a-t-il un suivi ORL ?"));
check("après envoi groupé : seule la question non répondue reste",
  cards().length === 1 && qTexts()[0].includes("attentionnelle"));
check("total d'appels LLM = 3 (dictée + 1 réponse + 1 groupé)", structureCalls.length === 3);

// === Round 4 : erreur serveur → rien n'est perdu ==============================
inputs()[0].value = "oui, plainte attentionnelle";
structureResponder = () => ({ __status: 500, detail: "Ollama indisponible" });
ansBtns()[0].click();
await settle();
check("erreur serveur : la question n'est PAS supprimée", __t.QS.length === 1 && cards().length === 1);
check("erreur serveur : la réponse saisie est intacte", inputs()[0].value === "oui, plainte attentionnelle");
check("erreur serveur : boutons ré-activés pour réessayer",
  !ansBtns()[0].disabled && !document.getElementById("structBtn").disabled);
check("erreur serveur : message affiché", status().includes("Erreur"));

// === Round 5 : chrono pendant l'analyse ======================================
structureResponder = () => ({
  bilan: structuredClone(CUR0),
  questions: [
    { section: "", question: "Quel est le niveau scolaire ?", pourquoi: "" },
    { section: "", question: "Des antécédents familiaux ?", pourquoi: "" },
    // déjà répondue au round 2 : malgré la consigne, l'IA la repose → filtrée côté client
    { section: "", question: "Y a-t-il un suivi ORL ?", pourquoi: "" },
  ],
});
holdNext = new Promise((r) => setTimeout(r, 1400));
ansBtns()[0].click();
await new Promise((r) => setTimeout(r, 1200));
check("chrono : le temps écoulé défile pendant l'analyse", /Analyse en cours… \d+ s/.test(status()));
await new Promise((r) => setTimeout(r, 400));
holdNext = null;
check("chrono : arrêté après l'analyse (message final)", status().includes("réponse(s) intégrée(s)"));
check("2 nouvelles questions affichées — la question DÉJÀ RÉPONDUE reposée est filtrée",
  cards().length === 2 && !qTexts().some((t) => t.includes("ORL")));

// === Round 6 : dicter une réponse au micro ===================================
micBtns()[0].click();
await settle();
check("micro : bouton actif passe en ■ (rouge)",
  micBtns()[0].textContent === "■" && micBtns()[0].classList.contains("rec"));
check("micro : l'autre micro et la dictée principale sont en attente",
  micBtns()[1].disabled && document.getElementById("recBtn").disabled);
micBtns()[0].click(); // stop → transcription
await settle();
check("micro : transcription insérée dans le champ de la question",
  inputs()[0].value === "sept ans et demi");
check("micro : bouton revenu à 🎤 et tout ré-activé",
  micBtns()[0].textContent === "🎤" && !micBtns()[1].disabled
  && !document.getElementById("recBtn").disabled);
inputs()[1].value = "aucun antécédent";
inputs()[1].dispatchEvent(new Event("input"));
check("micro : la réponse dictée compte pour l'envoi groupé",
  document.getElementById("qSendAll").textContent === "Envoyer les 2 réponses");

// === Round 7 : écarter une question ==========================================
const callsBefore = structureCalls.length;
dropBtns()[1].click(); // écarte « antécédents familiaux »
check("écarter : la question disparaît sans appel LLM",
  cards().length === 1 && !qTexts().some((t) => t.includes("antécédents"))
  && structureCalls.length === callsBefore);
check("écarter : le brouillon de l'autre question survit", inputs()[0].value === "sept ans et demi");
structureResponder = () => ({
  bilan: structuredClone(CUR0),
  questions: [
    { section: "", question: "Des antécédents familiaux ?", pourquoi: "" },
    { section: "", question: "Le patient est-il suivi en psychomotricité ?", pourquoi: "" },
  ],
});
ansBtns()[0].click();
await settle();
check("écarter : l'IA ne repose PAS une question écartée",
  cards().length === 1 && qTexts()[0].includes("psychomotricité"));
check("écarter : le texte original des écartées est envoyé au LLM",
  structureCalls.at(-1).questions_ecartees.includes("Des antécédents familiaux ?"));

// === Round 8 : écarter la question pendant son enregistrement ================
micBtns()[0].click();
await settle();
check("micro actif avant écartement", __t.ansRec !== null);
dropBtns()[0].click(); // écarte la question en cours de dictée
await settle();
check("micro orphelin coupé, panneau vidé proprement",
  __t.ansRec === null && cards().length === 0
  && !document.getElementById("recBtn").disabled);

// === Round 9 : nouvelle dictée avec question ouverte → elle persiste =========
structureResponder = () => ({
  bilan: structuredClone(CUR0),
  questions: [{ section: "", question: "Quelle est la latéralité ?", pourquoi: "" }],
});
document.getElementById("dicteeText").value = "nouvelle dictée";
document.getElementById("structBtn").click();
await settle();
check("dictée : 1 question ouverte affichée", cards().length === 1);
structureResponder = () => ({
  bilan: structuredClone(CUR0),
  questions: [{ section: "", question: "Une gêne auditive est-elle rapportée ?", pourquoi: "" }],
});
document.getElementById("dicteeText").value = "suite de la dictée";
document.getElementById("structBtn").click();
await settle();
check("dictée suivante : la question ouverte PERSISTE, envoyée « en attente »",
  cards().length === 2 && qTexts()[0].includes("latéralité")
  && structureCalls.at(-1).questions_en_attente.includes("Quelle est la latéralité ?"));
check("dictée suivante : nouvelle question ajoutée à la suite", qTexts()[1].includes("auditive"));
check("dictée envoyée : champ vidé après succès", document.getElementById("dicteeText").value === "");

console.log(failures ? `\n${failures} échec(s)` : "\nTous les scénarios passent.");
process.exit(failures ? 1 : 0);

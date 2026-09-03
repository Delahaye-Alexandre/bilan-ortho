// Test fonctionnel de l'écran ⚙️ Paramètres (plan « Paramètres compréhensibles »,
// docs/plan-parametres-2026-09-03.md) : sommaire, bulles d'aide, valeur
// recommandée et pastille « modifié », listes à choix, aperçus vivants, bloc
// technique replié, retour aux valeurs recommandées par section, aller-retour
// affichage → enregistrement (rien ne s'affiche sans se sauvegarder).
// Lancer : bun tests/ui/test_parametres_ui.mjs
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register();

const HTML_PATH = new URL("../../app/static/index.html", import.meta.url).pathname;
const html = await Bun.file(HTML_PATH).text();
const scriptStart = html.indexOf("<script>");
const scriptEnd = html.indexOf("</script>");
const scriptBody = html.slice(scriptStart + "<script>".length, scriptEnd);
const markup = html.slice(0, scriptStart) + html.slice(scriptEnd + "</script>".length);
document.documentElement.innerHTML = markup;

// --- Stubs micro et confirmation ---------------------------------------------
class FakeMediaRecorder { constructor(s) { this.stream = s; } state = "inactive"; start() {} stop() {} }
globalThis.MediaRecorder = FakeMediaRecorder;
const fakeStream = { getTracks: () => [{ stop() {} }] };
try {
  Object.defineProperty(navigator, "mediaDevices", { value: { getUserMedia: async () => fakeStream }, configurable: true });
} catch { navigator.mediaDevices = { getUserMedia: async () => fakeStream }; }
globalThis.confirm = () => true;

// --- Stub réseau -------------------------------------------------------------
const DEFAUTS = {
  praticien: { nom: "", prenom: "", titre: "Orthophoniste", adeli: "", rpps: "", siret: "", adresse: "",
               code_postal: "", ville: "", telephone: "", email: "", lieu_signature: "" },
  llm: { model: "qwen2.5:7b-instruct-q4_K_M", temperature: 0.3 },
  stt: { device: "auto", model: "auto", beam_size: 5, vad: true, language: "fr",
         hotwords: ["orthophonie", "bilan"], corrections: {} },
  style: { few_shot_k: 4, niveau_detail: "standard", vouvoiement: true, mise_en_forme_ia: true },
  embeddings: { model: "nomic-embed-text" },
  seuils: { fragilite_et: -1, pathologique_et: -1.5, severe_et: -2,
            fragilite_percentile: 16, pathologique_percentile: 7, severe_percentile: 2 },
  cotation: { valeur_amo: 2.6, bilan_simple_coeff: 24, bilan_complexe_coeff: 34, renouvellement_coeff: 30 },
  rgpd: { verrouillage_inactivite_minutes: 15, conservation_jours: 0, dictee_max_minutes: 30 },
  sauvegarde: { dossier: "", retention: 10, auto_jours: 7 },
  maj: { verification_auto: false },
  trame: { sections: [{ cle: "anamnese", titre: "Anamnèse" }, { cle: "epreuves", titre: "Épreuves" }] },
  catalogues: {}, prompts: { structure_system: "" },
};
// Configuration effective : quelques écarts aux défauts, dont des valeurs hors liste.
const CFG = structuredClone(DEFAUTS);
CFG.style.few_shot_k = 7;        // hors liste → « personnalisé »
CFG.sauvegarde.auto_jours = 3;   // hors liste
CFG.llm.model = "qwen3.5:9b";    // configuré mais non installé (cf. /api/models)
CFG.stt.corrections = { ortofonie: "orthophonie" };

const configPuts = [], deletes = [];
const rep = (r) => ({ ok: true, status: 200, json: async () => r });
globalThis.fetch = async (p, o = {}) => {
  const url = String(p);
  if (url.includes("/api/config/defauts")) return rep(structuredClone(DEFAUTS));
  if (url.includes("/api/config/overrides")) return rep({});
  const mSec = url.match(/\/api\/config\/([a-z]+)(\?cles=([^&]+))?$/);
  if (mSec && o.method === "DELETE") {
    deletes.push({ section: mSec[1], cles: mSec[3] ? decodeURIComponent(mSec[3]) : null });
    return rep(structuredClone(CFG));
  }
  if (url.endsWith("/api/config")) {
    if (o.method === "PUT") configPuts.push(JSON.parse(o.body).overrides);
    return rep(structuredClone(CFG));
  }
  if (url.includes("/api/models")) return rep({ models: ["qwen3.5:4b", "mistral:7b"], default: "qwen3.5:4b" });
  if (url.includes("/api/stt/info")) return rep({ model: "medium", device: "cpu", compute_type: "int8" });
  if (url.includes("/api/sauvegardes")) return rep({ dossier: "", derniere: null, fichiers: [] });
  if (url.includes("/api/domaines")) return rep([{ cle: "langage_oral", titre: "Langage oral" }]);
  if (url.includes("/api/catalogues/")) return rep({ guidance: "", tests: [] });
  if (url.includes("/api/prompts/structure-defaut")) return rep({ prompt: "CONSIGNE {cles}" });
  return rep({});
};

const body = scriptBody.replace(/gate\(\);\s*$/, "") + `
;globalThis.__t = { CHAMPS, collectSettings, fillSettings };`;
new Function(body)();

const settle = () => new Promise((r) => setTimeout(r, 30));
let failures = 0;
const check = (label, cond) => {
  console.log(`${cond ? "OK   " : "ECHEC"} ${label}`);
  if (!cond) failures++;
};
const $ = (id) => document.getElementById(id);
const modal = () => document.querySelector("#settingsOverlay .modal");
const bulleDe = (id) => $(`aide-${id}`);
const boutonDe = (id) => document.querySelector(`.aide[data-aide="${id}"]`);
const modifDe = (id) => boutonDe(id).parentNode.querySelector(".modif");
const choisi = (sel) => [...sel.options].find((o) => o.selected) || sel.options[sel.selectedIndex];
const saisir = (id, v) => { $(id).value = v; $(id).dispatchEvent(new Event("input", { bubbles: true })); };

// === 1. Ouverture : focus sur le cabinet, bloc technique replié ==============
$("settingsBtn").click();
await settle();
check("ouverture : modale visible", $("settingsOverlay").hidden === false);
check("ouverture : focus sur le premier champ de « Mon cabinet »",
  document.activeElement === $("cfgPratPrenom"));
check("ouverture : bloc technique replié",
  $("techCorps").hidden === true && $("techToggle").getAttribute("aria-expanded") === "false");
const liens = [...document.querySelectorAll(".sommaire a")];
check("sommaire : sept sections, chacune présente dans la page",
  liens.length === 7 && liens.every((a) => $(a.getAttribute("href").slice(1)) !== null));

// === 2. Chaque réglage a sa bulle ============================================
const champs = [...modal().querySelectorAll('input[id^="cfg"], select[id^="cfg"], textarea[id^="cfg"]')]
  .filter((el) => !el.closest("#secCabinet"));
check("au moins trente champs hors identité", champs.length >= 30);
const sansAide = champs.filter((el) => {
  const t = el.getAttribute("aria-describedby") && $(el.getAttribute("aria-describedby"));
  return !(t && t.getAttribute("role") === "tooltip" && t.textContent.trim().length > 20);
});
if (sansAide.length) console.log("   sans aide :", sansAide.map((e) => e.id).join(", "));
check("chaque champ hors identité a une bulle (aria-describedby → role=tooltip)", sansAide.length === 0);
check("identité : explication en tête de section",
  $("secCabinet").querySelector("p").textContent.includes("rien n'est inventé"));
check("registre CHAMPS : chaque ancre existe dans la page",
  Object.keys(__t.CHAMPS).every((id) => $(id) !== null));
check("chaque bouton ⓘ est étiqueté pour les lecteurs d'écran",
  [...modal().querySelectorAll(".aide[data-aide]")].every((b) => b.getAttribute("aria-label").startsWith("Aide : ")));

// === 3. Vocabulaire : aucun mot de code hors bloc technique =================
const motsDeCode = /LLM|VAD|beam|regex|embedding|cuda|Whisper|temp[ée]rature|0 = /i;
const fautifs = [...modal().querySelectorAll("label, legend, .soustitre, .sommaire a")]
  .filter((el) => !el.closest("#techCorps") && motsDeCode.test(el.textContent));
if (fautifs.length) console.log("   fautifs :", fautifs.map((e) => e.textContent.trim()).join(" | "));
check("aucun mot de code dans les libellés hors bloc technique", fautifs.length === 0);
check("« Vouvoiement » retiré de l'écran", !modal().textContent.includes("ouvoiement"));

// === 4. Bulle : épinglage au clic, Échap en deux temps =======================
boutonDe("cfgRgpdLock").click();
check("bulle épinglée au clic",
  bulleDe("cfgRgpdLock").classList.contains("ouverte")
  && boutonDe("cfgRgpdLock").getAttribute("aria-expanded") === "true");
check("valeur recommandée lue sur le serveur, en clair",
  bulleDe("cfgRgpdLock").textContent.includes("Recommandé : 15 minutes"));
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
check("Échap : la bulle se ferme, la modale reste",
  !bulleDe("cfgRgpdLock").classList.contains("ouverte") && $("settingsOverlay").hidden === false);
document.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
check("second Échap : la modale se ferme", $("settingsOverlay").hidden === true);
$("settingsBtn").click();
await settle();
boutonDe("cfgStyleK").click();
boutonDe("cfgSauvRet").click();
check("une seule bulle épinglée à la fois",
  document.querySelectorAll(".bulle.ouverte").length === 1 && bulleDe("cfgSauvRet").classList.contains("ouverte"));
$("secCotation").click();
check("clic ailleurs : bulle refermée", document.querySelectorAll(".bulle.ouverte").length === 0);

// === 5. Pastilles « modifié » ===============================================
check("extraits = 7 ≠ 4 → « modifié »", modifDe("cfgStyleK").hidden === false);
check("verrouillage au défaut → pas de pastille", modifDe("cfgRgpdLock").hidden === true);
check("corrections ajoutées → « modifié »", modifDe("cfgSttCorr").hidden === false);
check("recommandé pour le vocabulaire : la liste intégrée",
  bulleDe("cfgSttHotwords").textContent.includes("liste intégrée (2 termes)"));
check("recommandé pour l'AMO : en euros", bulleDe("cfgCotAmo").textContent.includes("Recommandé : 2,60 €"));

// === 6. Listes à choix ======================================================
check("verrouillage : libellés en clair, valeur courante sélectionnée",
  [...$("cfgRgpdLock").options].map((o) => o.textContent).join("|") === "5 minutes|15 minutes|30 minutes|1 heure|jamais"
  && $("cfgRgpdLock").value === "15");
check("extraits = 7 hors liste → « 7 extraits (personnalisé) » sélectionné",
  choisi($("cfgStyleK")).textContent === "7 extraits (personnalisé)" && $("cfgStyleK").value === "7");
check("sauvegarde auto = 3 jours → personnalisé",
  choisi($("cfgSauvAuto")).textContent === "tous les 3 jours (personnalisé)");
check("conservation : jamais / 1 an / 2 ans / 5 ans",
  [...$("cfgRgpdCons").options].map((o) => o.textContent).join("|") === "jamais|1 an|2 ans|5 ans");

// === 7. Aperçus vivants =====================================================
check("cotation : montant calculé", $("cotApercu").textContent.includes("Bilan simple : 24 × 2,60 € = 62,40 €"));
saisir("cfgCotAmo", "2.8");
check("cotation : recalcul à la frappe", $("cotApercu").textContent.includes("24 × 2,80 € = 67,20 €"));
check("seuils : quatre scores d'exemple classés",
  /−0,7 ET → norme.*−1,2 ET → fragilité.*−1,7 ET → pathologique.*−2,4 ET → sévère/.test($("seuilApercu").textContent));
check("seuils : percentiles aussi, ordinal correct", $("seuilApercu").textContent.includes("20e percentile → norme") && $("seuilApercu").textContent.includes("1er percentile → sévère"));
saisir("cfgSeuilFrag", "-2.5");
check("seuils dans le désordre : avertissement en clair", $("seuilApercu").textContent.startsWith("⚠️"));
saisir("cfgSeuilFrag", "-1");
check("identité vide : aperçu explicite", $("pratApercu").textContent.includes("sans en-tête"));
$("cfgPratPrenom").value = "Camille"; $("cfgPratVille").value = "Lille";
saisir("cfgPratNom", "Martin");
check("identité : signature aperçue",
  $("pratApercu").textContent === "Signature : Camille Martin, Orthophoniste · Fait à Lille");
check("dictée : état en clair", $("sttEtat").textContent.includes("modèle medium, sur le processeur"));
check("modèle d'IA : liste des modèles installés, configuré non installé signalé",
  $("cfgLlmModel").value === "qwen3.5:9b"
  && choisi($("cfgLlmModel")).textContent.includes("non installé")
  && $("cfgLlmModel").options.length === 3);

// === 8. Bloc technique et sommaire ==========================================
$("techToggle").click();
check("bouton : bloc technique ouvert",
  $("techCorps").hidden === false && $("techToggle").getAttribute("aria-expanded") === "true");
$("techToggle").click();
check("bouton : bloc technique refermé", $("techCorps").hidden === true);
liens[liens.length - 1].click();
check("sommaire → réglages techniques : bloc ouvert, section focalisée",
  $("techCorps").hidden === false && document.activeElement === $("secTech"));
check("les champs techniques vivent dans le bloc replié",
  ["cfgLlmModel", "cfgLlmTemp", "cfgEmbModel", "cfgSttDevice", "cfgSttModel", "cfgSttBeam",
   "cfgSttLang", "cfgSttVad", "promptTexte", "cfgReset"].every((id) => $(id).closest("#techCorps") !== null));
check("trame sous « Mes comptes-rendus », catalogues sous « Mes tests et seuils »",
  $("trameListe").closest("#secRedaction") !== null && $("catTests").closest("#secSeuils") !== null);

// === 9. Enregistrement : aller-retour complet ===============================
$("cfgSave").click();
await settle();
check("PUT envoyé", configPuts.length === 1);
const envoye = configPuts[0] || {};
check("valeurs personnalisées renvoyées telles quelles (7 extraits, 3 jours)",
  envoye.style.few_shot_k === 7 && envoye.sauvegarde.auto_jours === 3);
check("listes à choix → nombres",
  envoye.rgpd.verrouillage_inactivite_minutes === 15 && envoye.rgpd.dictee_max_minutes === 30
  && envoye.rgpd.conservation_jours === 0);
check("vouvoiement absent de l'enregistrement (valeur enregistrée conservée)", !("vouvoiement" in envoye.style));
check("mise en forme par l'assistant renvoyée", envoye.style.mise_en_forme_ia === true);
check("modèle non installé renvoyé tel quel", envoye.llm.model === "qwen3.5:9b");
check("corrections relues", JSON.stringify(envoye.stt.corrections) === JSON.stringify({ ortofonie: "orthophonie" }));
const lire = (o, ch) => ch.split(".").reduce((x, k) => (x == null ? undefined : x[k]), o);
const nonRenvoyes = Object.values(__t.CHAMPS).map((c) => c.chemin).filter((ch) => ch && lire(envoye, ch) === undefined);
if (nonRenvoyes.length) console.log("   non renvoyés :", nonRenvoyes.join(", "));
check("tout réglage affiché est renvoyé (rien ne s'affiche sans se sauvegarder)", nonRenvoyes.length === 0);

// === 10. Retour aux valeurs recommandées par section =======================
$("secSeuils").querySelector("[data-reset-btn]").click();
await settle();
check("seuils : DELETE /api/config/seuils", deletes.length === 1 && deletes[0].section === "seuils" && deletes[0].cles === null);
check("seuils : confirmation affichée", $("secSeuils").querySelector("[data-reset-st]").textContent.includes("✓"));
$("secDictee").querySelector("[data-reset-btn]").click();
await settle();
check("dictée : seules les clés du bloc (vocabulaire, corrections)",
  deletes[1] && deletes[1].section === "stt" && deletes[1].cles === "hotwords,corrections");
$("secSecurite").querySelector("[data-reset-btn]").click();
await settle();
check("sécurité : rgpd, sauvegarde et mises à jour", deletes.slice(2).map((d) => d.section).join(",") === "rgpd,sauvegarde,maj");
globalThis.confirm = () => false;
deletes.length = 0;
$("secCotation").querySelector("[data-reset-btn]").click();
await settle();
check("confirmation refusée : aucun appel", deletes.length === 0);

console.log(failures ? `\n${failures} échec(s)` : "\nTous les tests passent.");
process.exit(failures ? 1 : 0);

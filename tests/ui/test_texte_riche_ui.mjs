// Test fonctionnel du texte riche des rubriques (lot A du plan « mise en forme ») :
// conversions Markdown restreint <-> DOM, rendu, enregistrement, brouillons,
// collage depuis Word / Google Docs, copie texte + HTML, réglage Paramètres.
// Charge la vraie page dans happy-dom. Lancer : bun tests/ui/test_texte_riche_ui.mjs
import { GlobalRegistrator } from "@happy-dom/global-registrator";

GlobalRegistrator.register();

const HTML_PATH = new URL("../../app/static/index.html", import.meta.url).pathname;
const html = await Bun.file(HTML_PATH).text();
const scriptStart = html.indexOf("<script>");
const scriptEnd = html.indexOf("</script>");
const scriptBody = html.slice(scriptStart + "<script>".length, scriptEnd);
document.documentElement.innerHTML = html.slice(0, scriptStart) + html.slice(scriptEnd + "</script>".length);

// --- Stub réseau : on capture les enregistrements de rubriques ---------------
const sectionPuts = [];
globalThis.fetch = async (p, o = {}) => {
  if (String(p).includes("/sections/") && o.method === "PUT") {
    sectionPuts.push({ url: String(p), body: JSON.parse(o.body) });
    return { ok: true, json: async () => ({}) };
  }
  return { ok: true, json: async () => ({}) };
};
globalThis.confirm = () => true;
globalThis.alert = () => {};

const body = scriptBody.replace(/gate\(\);\s*$/, "") + `
;globalThis.__t = {
  get CUR() { return CUR; }, set CUR(v) { CUR = v; },
  renderBilan, sectionsNonEnregistrees,
  rtAnalyser, rtSerialiser, rtVersMd, remplirEditeur, rtHtmlVersBlocs, rtBlocsVersHtml, rtEnClair,
};`;
new Function(body)();
const __t = globalThis.__t;

let failures = 0;
const check = (label, cond) => {
  console.log(`${cond ? "OK   " : "ECHEC"} ${label}`);
  if (!cond) failures++;
};
const settle = () => new Promise((r) => setTimeout(r, 0));
const secEd = (cle) => document.querySelector(`#bilanView .sec[data-cle="${cle}"] .secText`);

// === 1. Conversions : mêmes échantillons que tests/test_texte_riche.py =======
// (forme canonique attendue identique côté Python — c'est ce qui garantit que
// l'éditeur et les exports lisent la même chose)
const ECHANTILLONS = [
  ["Texte brut.", "Texte brut."],
  ["Le test **Alouette** est *chuté* : <u>Compréhension</u> :\n- a\n* b\n• c\nSuite.",
   "Le test **Alouette** est *chuté* : <u>Compréhension</u> :\n\n- a\n- b\n- c\n\nSuite."],
  ["5 * 3 = 15 et (*) note, **non fermé", "5 * 3 = 15 et (*) note, **non fermé"],
  ["Axes :\n1. phono\n2. lecture\n  suite de lecture\n\nParagraphe final.",
   "Axes :\n\n1. phono\n2. lecture\n  suite de lecture\n\nParagraphe final."],
  ["***gras ital*** et **gras *ital* fin**", "***gras ital*** et **gras** ***ital*** **fin**"],
  ["Écart :\n\\- 2 ET à l'Alouette", "Écart :\n\\- 2 ET à l'Alouette"],
  ["", ""],
];
for (const [entree, attendu] of ECHANTILLONS) {
  const canon = __t.rtSerialiser(__t.rtAnalyser(entree));
  check(`canonique : ${JSON.stringify(entree).slice(0, 40)}`, canon === attendu);
  check(`  … et stable`, __t.rtSerialiser(__t.rtAnalyser(canon)) === canon);
  const ed = document.createElement("div");
  __t.remplirEditeur(ed, entree);
  check(`  … et identique via le DOM`, __t.rtVersMd(ed) === attendu);
}
// Jamais d'injection : une balise dans le texte reste du texte.
{
  const ed = document.createElement("div");
  __t.remplirEditeur(ed, "Texte <script>alert(1)</script> et <b>faux gras</b>");
  check("balises du texte rendues comme du texte", !ed.querySelector("script") && !ed.querySelector("b")
    && ed.textContent.includes("<b>faux gras</b>"));
}

// === 2. Rendu d'un bilan : gras visible, référence canonique, pas de faux brouillon
const CUR0 = {
  id: "b1", statut: "brouillon", domaines: [], epreuves: [], patient: null,
  sections: [
    { cle: "anamnese", titre: "Anamnèse", statut: "propose_ia", contenu: "Le test **Alouette** est chuté.\n* item ancien" },
    { cle: "diagnostic", titre: "Diagnostic", statut: "vide", contenu: "" },
  ],
};
__t.CUR = structuredClone(CUR0);
__t.renderBilan();
check("rendu : le gras est un vrai <b> dans la zone éditable", !!secEd("anamnese").querySelector("b"));
check("rendu : la puce « * » ancienne devient une liste", !!secEd("anamnese").querySelector("ul li"));
check("rendu : zone éditable accessible (textbox, libellé = titre)",
  secEd("anamnese").getAttribute("role") === "textbox" && secEd("anamnese").getAttribute("aria-label") === "Anamnèse");
check("rendu : barre de mise en forme (5 boutons, libellés)",
  document.querySelectorAll('#bilanView .sec[data-cle="anamnese"] .rt-bar button').length === 5
  && !![...document.querySelectorAll('#bilanView .sec[data-cle="anamnese"] .rt-bar button')].find((b) => b.getAttribute("aria-label") === "Souligné (Ctrl+U)"));
check("pas de faux « modifié » sur un contenu non canonique", __t.sectionsNonEnregistrees().length === 0);

// === 3. Enregistrer envoie du Markdown restreint ==============================
__t.remplirEditeur(secEd("anamnese"), "Relu, **validé**.\n- axe 1\n- axe 2");
check("brouillon détecté après modification", __t.sectionsNonEnregistrees().map((b) => b.cle).join() === "anamnese");
document.querySelector('#bilanView .sec[data-cle="anamnese"] .save').click();
await settle();
check("PUT : contenu en Markdown restreint", sectionPuts.length === 1
  && sectionPuts[0].body.contenu === "Relu, **validé**.\n\n- axe 1\n- axe 2");
check("après enregistrement : plus de brouillon", __t.sectionsNonEnregistrees().length === 0);

// === 4. Un brouillon mis en forme survit au re-rendu ==========================
__t.remplirEditeur(secEd("anamnese"), "Correction <u>soulignée</u> non enregistrée");
__t.renderBilan();
check("re-rendu : brouillon conservé avec sa mise en forme",
  __t.rtVersMd(secEd("anamnese")) === "Correction <u>soulignée</u> non enregistrée"
  && document.querySelector('#bilanView .sec[data-cle="anamnese"] .savest').textContent.includes("non enregistrées"));

// === 5. Collage depuis Word / Google Docs : gras, souligné et listes gardés, le reste retiré
const WORD = `<html><head><style>p{color:red}</style></head><body>
<p class=MsoNormal>Le test <b>Alouette</b> est <span style='font-style:italic'>chuté</span>.<o:p></o:p></p>
<p class=MsoListParagraphCxSpFirst style='mso-list:l0 level1 lfo1'><!--[if !supportLists]--><span style='font-family:Symbol;mso-list:Ignore'>·<span style='font:7.0pt "Times New Roman"'>&nbsp;&nbsp;&nbsp; </span></span><!--[endif]-->phonologie</p>
<p class=MsoListParagraphCxSpLast style='mso-list:l0 level1 lfo1'><span style='mso-list:Ignore'>·<span>&nbsp; </span></span><u>lecture</u></p>
<b style="font-weight:normal" id="docs-internal-guid-1"><p><span style="font-weight:700">gras GDocs</span> normal</p></b>
<script>alert(1)</script></body></html>`;
const colle = __t.rtSerialiser(__t.rtHtmlVersBlocs(WORD));
check("collage Word : gras, italique, puces, souligné ; style et script retirés",
  colle === "Le test **Alouette** est *chuté*.\n\n- phonologie\n- <u>lecture</u>\n\n**gras GDocs** normal");
{
  const ed = secEd("diagnostic");
  const ev = new Event("paste", { bubbles: true, cancelable: true });
  ev.clipboardData = { getData: (t) => (t === "text/html" ? WORD : "texte brut") };
  ed.dispatchEvent(ev);
  check("collage dans la rubrique : structure insérée", __t.rtVersMd(ed).includes("- phonologie") && ev.defaultPrevented);
}

// === 6. Copier : texte brut ET HTML ===========================================
let clip = null;
globalThis.ClipboardItem = class { constructor(parts) { this.parts = parts; } };
navigator.clipboard.write = async (items) => { clip = items[0].parts; };
// Autre bilan : les brouillons des étapes précédentes (même dossier) ne
// doivent pas être proposés à l'enregistrement avant la copie.
const CUR6 = structuredClone(CUR0); CUR6.id = "b6";
__t.CUR = CUR6;
__t.renderBilan();
document.getElementById("copyBilan").click();
await settle(); await settle();
const clipTexte = clip && (await clip["text/plain"].text());
const clipHtml = clip && (await clip["text/html"].text());
check("copie : texte brut sans marqueurs", !!clipTexte && clipTexte.includes("ANAMNÈSE") && !clipTexte.includes("**"));
check("copie : HTML avec gras et liste", !!clipHtml && clipHtml.includes("<b>Alouette</b>") && clipHtml.includes("<ul><li>item ancien</li></ul>"));

// === 7. Paramètres : réglage « l'IA peut mettre en forme » ====================
check("Paramètres : case à cocher présente", !!document.getElementById("cfgStyleForme"));
check("rtEnClair : listes numérotées lisibles", __t.rtEnClair("1. a\n2. b") === "1. a\n2. b");

console.log(failures ? `\n${failures} scénario(s) en échec.` : "\nTous les scénarios passent.");
process.exit(failures ? 1 : 0);

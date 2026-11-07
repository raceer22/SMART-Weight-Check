// Builds submission/pitch_deck.pptx (P03-P05). Run from the repo root:
//   npm install pptxgenjs@3.12.0 react-icons@5.4.0 react@18.3.1 react-dom@18.3.1 sharp@0.33.5   (once, anywhere)
//   NODE_PATH=<that node_modules> node submission/deck_src/build_deck.js
// Every number on the slides comes from notes/FINDINGS.md and our_business_case/ (synthetic data).
const path = require("path");
const pptxgen = require("pptxgenjs");
const React = require("react");
const ReactDOMServer = require("react-dom/server");
const sharp = require("sharp");
const { FaWeightHanging, FaClipboardCheck, FaUserCheck } = require("react-icons/fa");

const ROOT = path.resolve(__dirname, "..", "..");
const IMG = (p) => path.join(ROOT, p);
const OUT = path.join(ROOT, "submission", "pitch_deck.pptx");

const THEME = {
  name: "Weigh at Source", headFontFace: "Arial", bodyFontFace: "Calibri",
  colors: {
    dk1: "1D2B27", lt1: "FFFFFF", dk2: "1F6F5A", lt2: "EEF3F1",
    accent1: "1F6F5A", accent2: "F2A541", accent3: "6B7570", accent4: "2A78D6", accent5: "B4493B", accent6: "9AA39F",
    hlink: "1F6F5A", folHlink: "6B7570",
  },
};
const HEX = THEME.colors;

async function icon(Comp, color = "#FFFFFF") {
  const svg = ReactDOMServer.renderToStaticMarkup(React.createElement(Comp, { size: 256, color }));
  const buf = await sharp(Buffer.from(svg)).png().toBuffer();
  return "image/png;base64," + buf.toString("base64");
}

(async () => {
  const pres = new pptxgen();
  pres.layout = "LAYOUT_WIDE"; // 13.33 x 7.5 in
  pres.theme = { headFontFace: THEME.headFontFace, bodyFontFace: THEME.bodyFontFace };
  pres.title = "SMART Weight Check";
  pres.subject = "Europress challenge, Since AI Hackathon 2026 (synthetic data)";
  const C = pres.SchemeColor;

  // ---------------------------------------------------------------- layouts
  pres.defineSlideMaster({
    title: "TITLE_DARK",
    background: { color: C.text2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.8, y: 2.0, w: 11.7, h: 1.5, fontSize: 54, bold: true, color: C.background1, valign: "bottom", align: "left", margin: 0 }, text: "" } },
      { placeholder: { options: { name: "body", type: "body", x: 0.8, y: 3.7, w: 11.0, h: 1.6, fontSize: 22, color: C.background2, valign: "top", margin: 0 }, text: "" } },
      { text: { text: "Since AI Hackathon 2026 · Europress challenge · all data synthetic, not Europress data", options: { x: 0.8, y: 6.7, w: 11.7, h: 0.4, fontSize: 12, color: C.background2, margin: 0 } } },
    ],
  });
  pres.defineSlideMaster({
    title: "CONTENT",
    background: { color: C.background1 },
    margin: [0.5, 0.6, 0.6, 0.6],
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.9, fontSize: 36, bold: true, color: C.text1, valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "SMART Weight Check · all data synthetic, not Europress data", options: { x: 0.6, y: 6.98, w: 9, h: 0.3, fontSize: 10, color: C.accent3, margin: 0 } } },
    ],
    slideNumber: { x: 12.2, y: 6.98, w: 0.5, h: 0.3, fontSize: 10, color: HEX.accent3, align: "right" },
  });
  pres.defineSlideMaster({
    title: "CLOSING_DARK",
    background: { color: C.text2 },
    objects: [
      { placeholder: { options: { name: "title", type: "title", x: 0.6, y: 0.35, w: 12.1, h: 0.9, fontSize: 36, bold: true, color: C.background1, valign: "middle", margin: 0 }, text: "" } },
      { text: { text: "SMART Weight Check · all data synthetic, not Europress data", options: { x: 0.6, y: 6.98, w: 9, h: 0.3, fontSize: 10, color: C.background2, margin: 0 } } },
    ],
    slideNumber: { x: 12.2, y: 6.98, w: 0.5, h: 0.3, fontSize: 10, color: HEX.lt2, align: "right" },
  });

  const text = (slide, t, o) => slide.addText(t, { isTextBox: true, margin: 0, fontSize: 15, color: C.text1, valign: "top", ...o });
  const card = (slide, x, y, w, h, name, fill = C.background2) =>
    slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h, rectRadius: 0.12, fill: { color: fill }, line: { type: "none" }, objectName: name });
  const badge = (slide, x, y, d, label, name) => {
    slide.addShape(pres.shapes.OVAL, { x, y, w: d, h: d, fill: { color: C.accent2 }, line: { type: "none" }, objectName: name });
    text(slide, label, { x, y, w: d, h: d, fontSize: 16, bold: true, align: "center", valign: "middle", color: C.text1, objectName: name + " label" });
  };
  const stat = (slide, x, y, w, big, small, name, bigColor = C.text2) => {
    text(slide, big, { x, y, w, h: 0.75, fontSize: 40, bold: true, color: bigColor, fontFace: THEME.headFontFace, objectName: name + " number" });
    text(slide, small, { x, y: y + 0.78, w, h: 0.62, fontSize: 14, color: C.text1, objectName: name + " label" });
  };
  const arrow = (slide, x1, y1, x2, y2, name, color = HEX.accent3) =>
    slide.addShape(pres.shapes.LINE, { x: x1, y: y1, w: x2 - x1, h: y2 - y1, line: { color, width: 2, endArrowType: "triangle" }, objectName: name });

  // ---------------------------------------------------------------- 1 title
  pres.addSection({ title: "Pitch" });
  let s = pres.addSlide({ masterName: "TITLE_DARK", sectionTitle: "Pitch" });
  s.addText("SMART Weight Check", { placeholder: "title" });
  s.addText([
    { text: "Weigh at source. Check every tonne.", options: { bold: true, breakLine: true } },
    { text: "An independent scale in the Europress compactor checks every lift and every per-tonne invoice line, and a human approves every proposal." },
  ], { placeholder: "body" });
  s.addNotes("0:00-0:15. Customers pay for waste by the lift and by the tonne, but the only scale they ever see belongs to their operator. SMART Weight Check puts an independent scale in the Europress compactor and checks every lift and every invoice line.");

  // ---------------------------------------------------------------- 2 problem
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Pitch" });
  s.addText("Customers pay per tonne they never see", { placeholder: "title" });
  s.addImage({ path: IMG("submission/img/story_charts.png"), x: 0.6, y: 1.5, w: 7.9, h: 7.9 * 430 / 1300, objectName: "CMP-00046 fill and weight charts", altText: "Fill % and weight kg of compactor CMP-00046, July to September 2026" });
  text(s, "CMP-00046 · cardboard · Lohja · Jul–Sep 2026. Top: fill % · bottom: container weight, kg (simulated). Dashed lines: trips without a lift.", { x: 0.6, y: 4.2, w: 7.9, h: 0.5, fontSize: 11, color: C.accent3, objectName: "chart caption" });
  card(s, 0.6, 4.95, 7.9, 1.7, "takeaway card");
  text(s, [
    { text: "July: the fill reading stuck at 88 % while the scale read ~0 kg. Four trucks came for nothing.", options: { breakLine: true } },
    { text: "Nobody did anything wrong. Nobody could see it.", options: { bold: true, color: C.text2 } },
  ], { x: 0.85, y: 5.15, w: 7.4, h: 1.35, fontSize: 18, valign: "middle", objectName: "takeaway text" });
  stat(s, 9.0, 1.5, 3.8, "2.3×", "€ per tonne vs the contract benchmark: €258 vs €110 (estimated)", "stat 1");
  stat(s, 9.0, 3.25, 3.8, "€346", "for 4 wasted trips while the fill reading was stuck (observed)", "stat 2");
  stat(s, 9.0, 5.0, 3.8, "6–25 %", "fill at three customer-ordered lifts in September (simulated)", "stat 3");
  s.addNotes("0:15-0:50. Meet compactor 46, a cardboard press in Lohja. In July its fill reading stuck at 88 % while the container scale read almost nothing: four trucks came for nothing, 346 euros of wasted-trip fees. In September the customer ordered three lifts at 6 to 25 % full. Over the quarter it paid 258 euros per tonne, 2.3 times its contract benchmark. Nobody did anything wrong. Nobody could see it. All of this is synthetic data.");

  // ---------------------------------------------------------------- 3 solution
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Pitch" });
  s.addText("Weigh, check, propose: a human decides", { placeholder: "title" });
  const steps = [
    [FaWeightHanging, "Weigh", "Four load cells under the container. Gross before the lift minus tare after = collected kg. A free zero check on every lift."],
    [FaClipboardCheck, "Check", "Every lift and every per-tonne invoice line against device weight, the operator's ticket and the contract. Combined loads and side waste are explained, not blamed."],
    [FaUserCheck, "Propose", "Each difference becomes a proposal with a reason and a check before acting. Approve, reject, undo. Nothing executes by itself."],
  ];
  for (let i = 0; i < 3; i++) {
    const x = 0.6 + i * 4.2;
    card(s, x, 1.55, 3.7, 3.55, `step ${i + 1} card`);
    s.addShape(pres.shapes.OVAL, { x: x + 0.3, y: 1.85, w: 0.85, h: 0.85, fill: { color: C.accent1 }, line: { type: "none" }, objectName: `step ${i + 1} icon circle` });
    s.addImage({ data: await icon(steps[i][0]), x: x + 0.5, y: 2.05, w: 0.45, h: 0.45, objectName: `step ${i + 1} icon` });
    text(s, `${i + 1} · ${steps[i][1]}`, { x: x + 0.3, y: 2.9, w: 3.1, h: 0.5, fontSize: 22, bold: true, fontFace: THEME.headFontFace, objectName: `step ${i + 1} title` });
    text(s, steps[i][2], { x: x + 0.3, y: 3.45, w: 3.1, h: 1.55, fontSize: 15, objectName: `step ${i + 1} text` });
    if (i < 2) arrow(s, x + 3.75, 3.3, x + 4.15, 3.3, `arrow ${i + 1}`);
  }
  text(s, "Every number carries its evidence:", { x: 0.6, y: 5.4, w: 12.1, h: 0.35, fontSize: 15, bold: true, objectName: "tags heading" });
  const tags = [["observed", "read from a record"], ["simulated", "SMART device data"], ["estimated", "our calculation"], ["hypothetical", "an assumption"]];
  tags.forEach(([t, d], i) => {
    const x = 0.6 + i * 3.1;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.85, w: 2.85, h: 0.75, rectRadius: 0.1, fill: { color: C.background1 }, line: { color: C.accent6, width: 1 }, objectName: `tag ${t}` });
    text(s, [{ text: t, options: { bold: true, color: C.text2, breakLine: true } }, { text: d, options: { fontSize: 13, color: C.accent3 } }],
      { x: x + 0.15, y: 5.9, w: 2.6, h: 0.65, fontSize: 15, valign: "middle", objectName: `tag ${t} text` });
  });
  s.addNotes("0:50-1:15. Our answer has three steps. Weigh: four load cells under the container. Check: every lift and every per-tonne invoice line against the device weight, the operator's ticket and the contract. Propose: every difference becomes a proposal with a reason and a check, and a human approves it. Nothing runs by itself.");

  // ---------------------------------------------------------------- 4 demo
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Pitch" });
  s.addText("Live demo: every lift checked", { placeholder: "title" });
  s.addImage({ path: IMG("submission/img/demo_weight_check.png"), x: 0.6, y: 1.45, w: 8.2, h: 8.2 * 880 / 1440, objectName: "weight check screenshot", altText: "App weight check for CMP-00042" });
  s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.45, w: 8.2, h: 8.2 * 880 / 1440, fill: { type: "none" }, line: { color: C.accent6, width: 1 }, objectName: "screenshot frame" });
  text(s, "Demo path", { x: 9.2, y: 1.45, w: 3.5, h: 0.45, fontSize: 20, bold: true, fontFace: THEME.headFontFace, objectName: "demo path heading" });
  const path4 = [
    "CMP-00046: the stuck fill line vs the flat weight line; 2.3× € per tonne",
    "CMP-00042: invoiced 2.94 t, container held 580 kg. A shared truck, split equally: re-split by device weight",
    "CMP-00047: no ticket, invoice 425 kg above the scale: ask for the ticket",
    "Approve, then undo",
  ];
  path4.forEach((t, i) => {
    badge(s, 9.2, 2.05 + i * 0.95, 0.42, String(i + 1), `demo step ${i + 1} badge`);
    text(s, t, { x: 9.75, y: 2.0 + i * 0.95, w: 3.0, h: 0.9, fontSize: 14, objectName: `demo step ${i + 1}` });
  });
  card(s, 9.2, 5.85, 3.5, 0.95, "quickstart result card");
  text(s, [{ text: "341 lifts checked: ", options: { bold: true } }, { text: "205 agree · 38 explained · 4 billing questions · 13 devices: check the scale" }],
    { x: 9.35, y: 5.9, w: 3.25, h: 0.85, fontSize: 13, valign: "middle", objectName: "quickstart result" });
  s.addNotes("1:15-2:30. LIVE DEMO: streamlit run app/app.py. 1) CMP-00046 opens: point at the stuck fill line vs the flat weight line, then 2.3x per tonne. 2) Switch to CMP-00042: this site was invoiced 2.94 tonnes for a container that held 580 kg. Two containers shared a truck and the net was split equally. The customer's total is right, but this site's euro per tonne is wrong; the device weight re-splits it. A fact, not blame. 3) CMP-00047: no ticket shared, the invoice says 425 kg more than the container weighed. Proposal: ask for the ticket. 4) Click Approve, then Undo: a human decides, and it can always be undone. If the demo fails, use the backup screenshots in the appendix.");

  // ---------------------------------------------------------------- 5 integration
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Pitch" });
  s.addText("From load cell to customer decision", { placeholder: "title" });
  const flow = [
    ["Weigh frame", "4 load cells → 4-channel ADC in the SMART cabinet"],
    ["SMART device", "existing controller and modem; hourly mass + lift events"],
    ["SMART cloud", "telemetry_hourly, collection_events: same schema as the dataset"],
    ["Weight Check engine", "contract cost per lift, weight check, early-lift rules"],
    ["Customer portal", "every proposal flagged “requires human approval”; approve, reject, undo"],
  ];
  flow.forEach(([h, d], i) => {
    const x = 0.6 + i * 2.5;
    card(s, x, 1.75, 2.15, 2.35, `flow ${i + 1}`, i === 3 ? C.text2 : C.background2);
    text(s, h, { x: x + 0.15, y: 1.9, w: 1.85, h: 0.75, fontSize: 17, bold: true, color: i === 3 ? C.background1 : C.text1, objectName: `flow ${i + 1} title` });
    text(s, d, { x: x + 0.15, y: 2.65, w: 1.85, h: 1.35, fontSize: 14, color: i === 3 ? C.background1 : C.text1, objectName: `flow ${i + 1} text` });
    if (i < 4) arrow(s, x + 2.18, 2.92, x + 2.47, 2.92, `flow arrow ${i + 1}`);
  });
  // inputs into the engine
  const ins = [["Customer", "contracts and invoices (upload or e-invoice feed)"], ["Operator", "weighbridge tickets, when shared"]];
  ins.forEach(([h, d], i) => {
    const x = 5.6 + i * 2.6;
    s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x: x - 0.55, y: 4.75, w: 2.45, h: 1.1, rectRadius: 0.1, fill: { color: C.background1 }, line: { color: C.accent6, width: 1 }, objectName: `input ${h}` });
    text(s, [{ text: h, options: { bold: true, breakLine: true } }, { text: d }], { x: x - 0.42, y: 4.82, w: 2.2, h: 0.95, fontSize: 14, valign: "middle", objectName: `input ${h} text` });
  });
  arrow(s, 6.1, 4.75, 8.0, 4.12, "customer input arrow");
  arrow(s, 8.7, 4.75, 8.3, 4.12, "operator input arrow");
  text(s, [
    { text: "Runs on what SMART already has: ", options: { bold: true } },
    { text: "the cabinet, the modem, the telemetry pipeline. The weight is the customer's own measurement; it is shared with the operator only with consent." },
  ], { x: 0.6, y: 6.1, w: 12.1, h: 0.7, fontSize: 15, objectName: "integration takeaway" });
  s.addNotes("2:30-2:50. It fits SMART as it is: the weighing module sits in the SMART cabinet, uses the existing modem, and its fields map one-to-one onto SMART telemetry and collection events. Proposals leave as an API payload that says: requires human approval.");

  // ---------------------------------------------------------------- 6 weight concept
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Pitch" });
  s.addText("A weigh frame under the container", { placeholder: "title" });
  s.addImage({ path: IMG("submission/img/weigh_frame_slide.png"), x: 0.6, y: 1.5, w: 8.3, h: 8.3 * 500 / 1140, objectName: "weigh frame illustration", altText: "Side view: load cells in rails under the press container, cable to the SMART controller" });
  card(s, 0.6, 5.35, 8.3, 1.4, "how a lift is weighed card");
  text(s, [
    { text: "How one lift is weighed: ", options: { bold: true } },
    { text: "stable gross reading with the ram idle, minus the tare when the empty container comes back. While the container is away the frame must read zero: a free zero check on every lift. Four separate cells reveal ice or debris under one corner." },
  ], { x: 0.8, y: 5.45, w: 7.9, h: 1.2, fontSize: 15, valign: "middle", objectName: "how a lift is weighed" });
  const facts = [
    ["σ 1.5 %", "design target; ~1.0 % accuracy budget (estimate)"],
    ["€1,200", "factory option · €3,400 installed retrofit (hypothetical BOM)"],
    ["Self-checking", "auto-zero every time the container leaves; span checked against the operator's tickets"],
    ["Validation", "2-week yard test with water tanks → 20-site pilot, 3 months → winter"],
  ];
  facts.forEach(([h, d], i) => {
    const y = 1.45 + i * 1.33;
    card(s, 9.2, y, 3.5, 1.18, `fact ${i + 1}`);
    text(s, h, { x: 9.38, y: y + 0.1, w: 3.2, h: 0.45, fontSize: i < 2 ? 24 : 18, bold: true, color: C.text2, fontFace: THEME.headFontFace, objectName: `fact ${i + 1} title` });
    text(s, d, { x: 9.38, y: y + 0.55, w: 3.2, h: 0.58, fontSize: 13, objectName: `fact ${i + 1} text` });
  });
  s.addNotes("2:50-3:25. The scale: four 10-tonne load cells in low-profile rails under the container. Every time the truck takes the container away, the frame reads zero, a free calibration check on every lift, and each lift is compared with the operator's own ticket to catch drift. Target accuracy 1.5 %. 1,200 euros as a factory option, 3,400 as a retrofit. Validation: a yard test with water tanks, a 20-site pilot, then a winter.");

  // ---------------------------------------------------------------- 7 accuracy is value
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Pitch" });
  s.addText("Accuracy decides what weight is worth", { placeholder: "title" });
  const sig = ["0.5 %", "1 %", "1.5 %", "1.75 %", "2.5 %", "5 %", "10 %"];
  s.addChart(pres.charts.LINE, [
    { name: "3 t loads within ±100 kg (%)", labels: sig, values: [100.0, 99.8, 98.3, 94.8, 82.1, 53.2, 25.9] },
    { name: "+10 % overbilling detected (%)", labels: sig, values: [94.7, 94.7, 95.0, 94.6, 92.5, 46.7, 15.6] },
  ], {
    x: 0.6, y: 1.45, w: 7.9, h: 5.3, objectName: "accuracy value chart",
    chartColors: [C.accent1, C.accent2], lineSize: 3, lineDataSymbol: "circle", lineDataSymbolSize: 8,
    showTitle: true, title: "Scale accuracy (σ, % of load) vs what it lets you check", titleFontSize: 14, titleColor: C.text1, titleFontFace: "+mn-lt",
    showLegend: true, legendPos: "b", legendFontSize: 12, legendFontFace: "+mn-lt", legendColor: C.text1,
    catAxisLabelColor: C.accent3, valAxisLabelColor: C.accent3, catAxisLabelFontSize: 12, valAxisLabelFontSize: 12,
    catAxisLabelFontFace: "+mn-lt", valAxisLabelFontFace: "+mn-lt",
    valAxisMinVal: 0, valAxisMaxVal: 100, valAxisMajorUnit: 25,
    valGridLine: { color: "DDE3E0", size: 0.75 }, catGridLine: { style: "none" },
    showValue: false,
  });
  text(s, "Competition data, 10,342 shared single-load tickets; examples/weighing_accuracy_value.py (estimated)", { x: 0.6, y: 6.75, w: 7.9, h: 0.25, fontSize: 10, color: C.accent3, objectName: "chart source" });
  stat(s, 9.0, 1.5, 3.8, "≤ 1.75 %", "keeps ≥ 95 % of 3 t loads within ±100 kg: the challenge target", "stat a");
  stat(s, 9.0, 3.2, 3.8, "> 2.5 %", "and checking the operator's tonnage stops working", "stat b", C.accent5);
  stat(s, 9.0, 4.9, 3.8, "7 %", "best estimate without a scale (ML or rotating kit): a free value scan, not an invoice check", "stat c", C.accent3);
  s.addNotes("3:25-3:50. Why a real scale? At 1.5 % accuracy, 98 % of 3-tonne loads land within plus or minus 100 kg and 95 % of 10 % overbilling is caught. Above 2.5 % that collapses. We tried estimating weight without a scale: 7 % at best. Good for a trend, so it becomes our free value scan, but not good enough to check an invoice.");

  // ---------------------------------------------------------------- 8 business model
  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Pitch" });
  s.addText("€15 per device-month, priced from value", { placeholder: "title" });
  stat(s, 0.6, 1.5, 3.9, "€36", "median realisable value per device-month (estimated): the customer keeps 2.4× the fee", "stat value");
  stat(s, 0.6, 3.15, 3.9, "2.0 years", "payback of onboarding at €15 and 25 % adoption (hypothetical)", "stat payback");
  text(s, "Yearly profit after onboarding, € (hypothetical, 52 synthetic customers)", { x: 4.9, y: 1.5, w: 7.8, h: 0.35, fontSize: 14, bold: true, objectName: "table heading" });
  const hdr = (t) => ({ text: t, options: { bold: true, color: C.background1, fill: { color: C.text2 }, align: "center" } });
  const cell = (t, hi = false) => ({ text: t, options: { align: "center", bold: hi, fill: { color: hi ? C.accent2 : C.background1 } } });
  s.addTable([
    [hdr("price / adoption"), hdr("10 %"), hdr("25 %"), hdr("40 %")],
    [cell("€10"), cell("943"), cell("2,358"), cell("3,773")],
    [cell("€15", true), cell("2,148"), cell("5,370", true), cell("8,592")],
    [cell("€25"), cell("1,735"), cell("4,338"), cell("6,941")],
  ], { x: 4.9, y: 1.95, w: 7.8, colW: [2.4, 1.8, 1.8, 1.8], rowH: 0.48, fontSize: 15, color: C.text1, border: { type: "solid", color: HEX.accent6, pt: 0.75 }, valign: "middle", objectName: "sensitivity table" });
  text(s, [{ text: "Price matters most. ", options: { bold: true } }, { text: "€15 maximises fee revenue; at €10 small customers cost more to support than they pay (6.5-year payback)." }],
    { x: 4.9, y: 4.0, w: 7.8, h: 0.75, fontSize: 15, objectName: "table takeaway" });
  const bm = [
    ["Sell to fleets of 6+ devices", "16+ devices: ~€4.0 k profit per customer-year; 2–5 devices lose money at €50 support"],
    ["Weigh where it pays", "factory option pays back in 2.9 years at the median device, retrofit in 8.2"],
    ["Hypothesis: per-tonne full service", "3 % margin ≈ €156 k/year on this sample; needs verified weight and a new role"],
  ];
  bm.forEach(([h, d], i) => {
    const x = 0.6 + i * 4.1;
    card(s, x, 5.0, 3.85, 1.75, `model card ${i + 1}`, i === 2 ? C.background1 : C.background2);
    if (i === 2) s.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y: 5.0, w: 3.85, h: 1.75, rectRadius: 0.12, fill: { type: "none" }, line: { color: C.accent2, width: 1.5, dashType: "dash" }, objectName: "hypothesis outline" });
    text(s, h, { x: x + 0.2, y: 5.12, w: 3.45, h: 0.45, fontSize: 16, bold: true, color: C.text2, objectName: `model card ${i + 1} title` });
    text(s, d, { x: x + 0.2, y: 5.6, w: 3.45, h: 1.05, fontSize: 14, objectName: `model card ${i + 1} text` });
  });
  s.addNotes("3:50-4:30. Price: 15 euros per device per month. The median customer can realise about 36 euros per device-month, so they keep 2.4 times the fee. Price matters most: at 10 euros it takes six and a half years to earn back the onboarding, at 15 two years. And the scale should go where it pays: the factory option pays back in under three years for half the devices, a retrofit only for the top ones. The big prize, a per-tonne full service with Europress in the middle, needs verified weight first. That's a hypothesis, and we label it that way.");

  // ---------------------------------------------------------------- 9 limits and next steps
  s = pres.addSlide({ masterName: "CLOSING_DARK", sectionTitle: "Pitch" });
  s.addText("What we have not proven, and next steps", { placeholder: "title" });
  text(s, "Not proven", { x: 0.6, y: 1.5, w: 6.0, h: 0.5, fontSize: 22, bold: true, color: C.accent2, fontFace: THEME.headFontFace, objectName: "not proven heading" });
  const np = [
    "that customers pay €15 per device-month: no interviews yet",
    "that the savings are real: synthetic world, hypothetical tariffs",
    "that the frame reaches σ 1.5 % on a real compactor in winter",
    "the hardware cost: indicative BOM, no supplier quotes",
    "that operators accept device weight as evidence",
  ];
  text(s, np.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < np.length - 1 } })),
    { x: 0.6, y: 2.1, w: 6.0, h: 3.6, fontSize: 17, color: C.background1, paraSpaceAfter: 10, objectName: "not proven list" });
  text(s, "Next steps", { x: 7.2, y: 1.5, w: 5.5, h: 0.5, fontSize: 22, bold: true, color: C.accent2, fontFace: THEME.headFontFace, objectName: "next steps heading" });
  const ns = ["10 customer interviews: willingness to pay", "2-week yard test: water-tank steps, hooklift cycles", "20-site pilot, 3 months, vs weighbridge tickets"];
  ns.forEach((t, i) => {
    badge(s, 7.2, 2.2 + i * 1.0, 0.5, String(i + 1), `next step ${i + 1} badge`);
    text(s, t, { x: 7.9, y: 2.15 + i * 1.0, w: 4.8, h: 0.62, fontSize: 17, color: C.background1, valign: "middle", objectName: `next step ${i + 1}` });
  });
  text(s, "Weigh at source. Check every tonne.", { x: 0.6, y: 5.9, w: 12.1, h: 0.7, fontSize: 30, bold: true, color: C.background1, fontFace: THEME.headFontFace, objectName: "closing line" });
  s.addNotes("4:30-5:00. What we have not proven: that customers pay, that the savings are real, and that the frame reaches 1.5 % in a Finnish winter. So the next steps are ten customer interviews, a two-week yard test and a 20-site pilot. Weigh at source, check every tonne. Thank you.");

  // ---------------------------------------------------------------- appendix
  pres.addSection({ title: "Appendix" });
  const backup = [
    ["Backup: proposals, a human decides", "submission/img/backup_proposals.png", 820, "CMP-00046: proposals with a reason and a check; one approved, with Undo. Weight rules add the early lifts on 4 and 11 September."],
    ["Backup: a lift without a ticket", "notes/screenshots/05_weight_check_CMP-00047_no_ticket.png", 826, "CMP-00047: two lifts invoiced without a shared ticket differ from the device weight, so the proposal is to ask for the ticket. The scale-check note points at the device, not the operator."],
  ];
  for (const [title, img, hpx, cap] of backup) {
    s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Appendix" });
    s.addText(title, { placeholder: "title" });
    const h = 5.2, w = h * 1440 / hpx;
    s.addImage({ path: IMG(img), x: 0.6, y: 1.45, w, h, objectName: "backup screenshot", altText: title });
    s.addShape(pres.shapes.RECTANGLE, { x: 0.6, y: 1.45, w, h, fill: { type: "none" }, line: { color: C.accent6, width: 1 }, objectName: "screenshot frame" });
    text(s, cap, { x: 0.6 + w + 0.35, y: 1.45, w: 12.7 - (0.6 + w + 0.35), h: 2.6, fontSize: 15, objectName: "backup caption" });
    s.addNotes("Backup slide if the live demo fails. All screenshots: notes/screenshots/.");
  }

  s = pres.addSlide({ masterName: "CONTENT", sectionTitle: "Appendix" });
  s.addText("Run it, sources and licences", { placeholder: "title" });
  text(s, "Run the demo", { x: 0.6, y: 1.45, w: 6, h: 0.45, fontSize: 20, bold: true, fontFace: THEME.headFontFace, objectName: "run heading" });
  card(s, 0.6, 1.95, 12.1, 1.85, "commands card");
  text(s, [
    "python -m venv .venv && source .venv/bin/activate",
    'pip install -e ".[dev,app]"',
    "python baselines/b1_economic_calculator.py data/quickstart/public my_task_a.csv",
    "python baselines/b2_rules_anomaly.py data/quickstart/public my_task_b.csv",
    "streamlit run app/app.py",
  ].map((t, i, a) => ({ text: t, options: { breakLine: i < a.length - 1 } })), { x: 0.85, y: 2.05, w: 11.6, h: 1.65, fontSize: 13, fontFace: "Courier New", paraSpaceAfter: 3, valign: "middle", objectName: "commands" });
  text(s, "Where everything is", { x: 0.6, y: 3.95, w: 12.1, h: 0.45, fontSize: 20, bold: true, fontFace: THEME.headFontFace, objectName: "where heading" });
  const where = [
    "submission/1_WEIGHING_CONCEPT.md: sensor, BOM, calibration, validation",
    "submission/2_SOFTWARE_DEMO.md: walkthrough, SMART integration",
    "submission/3_BUSINESS_CASE.md: value, pricing, sensitivity, limits",
    "submission/THIRD_PARTY.md: every library, dataset and service, with licence",
    "notes/FINDINGS.md: every number with its source table or script",
  ];
  text(s, where.map((t, i) => ({ text: t, options: { bullet: true, breakLine: i < where.length - 1 } })), { x: 0.6, y: 4.45, w: 12.1, h: 1.6, fontSize: 14, paraSpaceAfter: 2, objectName: "where list" });
  text(s, "Data: Europress × Since AI synthetic dataset v1.0.1 (use per the hackathon rules). Code: Python with numpy, pandas, DuckDB, Streamlit, Altair, scikit-learn, matplotlib (BSD, MIT, Apache-2.0 and PSF-style licences, all allow commercial use). AI assistance: Claude (Anthropic) via Claude Code.",
    { x: 0.6, y: 6.15, w: 12.1, h: 0.7, fontSize: 12, color: C.accent3, objectName: "licence summary" });
  s.addNotes("Reference slide for the jury: how to run, where the documents are, and licences.");

  await pres.writeFile({ fileName: OUT });
  const { applyTheme } = require(process.env.APPLY_THEME);
  await applyTheme(OUT, THEME);
  console.log("wrote", OUT);
})().catch((e) => { console.error(e); process.exit(1); });

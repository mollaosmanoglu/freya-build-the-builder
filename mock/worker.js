// Freya Bank statement-debt mock: serves exactly the answers in test-customers.json,
// on the paths of the 2026-10-01 service contract (POST /voice/v1/<service>).
import DATA from "./test-customers.json";

const CUSTOMERS = Object.fromEntries(DATA.customers.map((c) => [String(c.customerNo), c]));
const DEFAULT_CUSTOMER = DATA.customers[0];
const CORS = { "Access-Control-Allow-Origin": "*" };

const SERVICES = {
  "cards.list": { key: "customerNo", notFound: [404, "FB_IVR_CHANNEL_102", "WARNING", "Müşteriye ait geçerli kart bilgisi bulunamadı."] },
  "cards.balance": { key: "cardNumber", notFound: [404, "FB_IVR_CHANNEL_120", "WARNING", "Kart bakiye servisi hatası: kart bulunamadı"] },
  "statement.week.get": { key: "cardNumber", notFound: [404, "FB_IVR_CHANNEL_121", "WARNING", "Kart bulunamadı"] },
  "statement.week.decide": { key: "cardNumber", week: true },
  "statement.week.change": { key: "cardNumber", week: true },
  "contact.email.get": { key: "customerNo", required: ["intAddressInfoType"] },
  "statement.pdf.send": { key: "customerNo", required: ["cardNumber", "currencyType", "statementDate", "emailAddress"], notFound: [404, "FB_IVR_CHANNEL_107", "WARNING", "Pdf dokümanı bulunamadı"] },
};

function json(body, status = 200) {
  return Response.json(body, { status, headers: CORS });
}

function guid() {
  return crypto.randomUUID().replaceAll("-", "");
}

function error(status, code, type, message) {
  const id = guid();
  return json({ result: { guid: id, returnCode: code, messageText: message, code, message, type,
    details: { guid: id, rootCause: status === 404 ? "NotFoundException" : "InvalidArgumentsException", errorOrigin: "ivr-gateway-test:ivr-channel-v0" } } }, status);
}

function invalid(field) {
  return error(400, "INVALID_ARGUMENTS_ERROR", "ERROR", `${field} cannot be empty`);
}

// The panel's "Test API Request" button sends variables without filling them in, e.g. "{{customerNumber}}".
function isTemplateVariable(value) {
  return typeof value === "string" && (value.includes("{{") || value.includes("%7B%7B"));
}

function isEmpty(value) {
  return value === undefined || value === null || String(value).trim() === "";
}

function cardsOf(customer) {
  return Object.keys(customer.services["cards.balance"] || {});
}

function ownerOf(card) {
  return DATA.customers.find((c) => cardsOf(c).includes(card));
}

async function answer(entry) {
  if (entry.delaySeconds) await new Promise((r) => setTimeout(r, entry.delaySeconds * 1000));
  return json(entry.response, entry.http);
}

async function serve(name, request) {
  const spec = SERVICES[name];
  let body;
  try { body = await request.json(); } catch { body = null; }
  const data = (body && typeof body.data === "object" && body.data) || {};

  let key = data[spec.key];
  if (isTemplateVariable(key)) key = spec.key === "customerNo" ? DEFAULT_CUSTOMER.customerNo : cardsOf(DEFAULT_CUSTOMER)[0];
  if (isEmpty(key)) return invalid(spec.key === "customerNo" ? "customer number" : "card number");
  key = String(key).trim();
  for (const field of spec.required || []) {
    if (isEmpty(data[field])) return invalid(field);
  }

  const customer = spec.key === "customerNo" ? CUSTOMERS[key] : ownerOf(key);
  let entry = customer && customer.services[name];
  if (entry && spec.key === "cardNumber") entry = entry[key];
  if (entry && spec.week) {
    let week = data.newStatementWeek;
    if (isTemplateVariable(week)) week = Object.keys(entry)[0];
    if (isEmpty(week)) return invalid("newStatementWeek");
    if (isEmpty(data.statementDay)) return invalid("statementDay");
    entry = entry[String(week).trim()];
  }
  if (!entry) return spec.notFound ? error(...spec.notFound) : error(400, "INVALID_ARGUMENTS_ERROR", "ERROR", "invalid arguments");
  return answer(entry);
}

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method === "OPTIONS") {
      return new Response(null, { headers: { ...CORS, "Access-Control-Allow-Methods": "GET, POST, OPTIONS", "Access-Control-Allow-Headers": "*" } });
    }
    if (request.method === "GET" && url.pathname === "/health") return json({ status: "ok" });
    const name = url.pathname.replace(/^\/voice\/v1\//, "");
    if (request.method === "POST" && SERVICES[name]) return serve(name, request);
    if (request.method === "POST" && url.pathname === "/oauth2/token") return json({ access_token: "test-token", token_type: "Bearer", expires_in: 1800 });
    return json({ error: "not found", paths: Object.keys(SERVICES).map((s) => `POST /voice/v1/${s}`) }, 404);
  },
};

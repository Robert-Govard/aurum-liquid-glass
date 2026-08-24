// Minimal RFC4180-ish CSV parser — handles quoted fields (with embedded
// delimiters/newlines, "" as an escaped quote) and auto-detects comma vs
// semicolon as the delimiter (many EU bank exports use ";"). No dependency
// pulled in for this; bank CSV exports don't need more than this covers.
export function parseCsv(text: string): string[][] {
  const firstLine = text.slice(0, text.search(/\r?\n/) === -1 ? text.length : text.search(/\r?\n/));
  const commaCount = (firstLine.match(/,/g) ?? []).length;
  const semicolonCount = (firstLine.match(/;/g) ?? []).length;
  const delimiter = semicolonCount > commaCount ? ";" : ",";

  const rows: string[][] = [];
  let row: string[] = [];
  let field = "";
  let inQuotes = false;

  for (let i = 0; i < text.length; i++) {
    const char = text[i];

    if (inQuotes) {
      if (char === '"') {
        if (text[i + 1] === '"') {
          field += '"';
          i += 1;
        } else {
          inQuotes = false;
        }
      } else {
        field += char;
      }
      continue;
    }

    if (char === '"') {
      inQuotes = true;
    } else if (char === delimiter) {
      row.push(field);
      field = "";
    } else if (char === "\r") {
      // skip — \n (below) closes the row
    } else if (char === "\n") {
      row.push(field);
      rows.push(row);
      row = [];
      field = "";
    } else {
      field += char;
    }
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field);
    rows.push(row);
  }

  return rows.filter((cells) => !(cells.length === 1 && cells[0].trim() === ""));
}

export const DATE_FORMATS = ["YYYY-MM-DD", "DD.MM.YYYY", "DD/MM/YYYY", "MM/DD/YYYY", "DD-MM-YYYY"] as const;
export type DateFormat = (typeof DATE_FORMATS)[number];

const DATE_PATTERNS: Record<DateFormat, { regex: RegExp; order: ["y" | "m" | "d", "y" | "m" | "d", "y" | "m" | "d"] }> = {
  "YYYY-MM-DD": { regex: /^(\d{4})-(\d{1,2})-(\d{1,2})$/, order: ["y", "m", "d"] },
  "DD.MM.YYYY": { regex: /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/, order: ["d", "m", "y"] },
  "DD/MM/YYYY": { regex: /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/, order: ["d", "m", "y"] },
  "MM/DD/YYYY": { regex: /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/, order: ["m", "d", "y"] },
  "DD-MM-YYYY": { regex: /^(\d{1,2})-(\d{1,2})-(\d{4})$/, order: ["d", "m", "y"] },
};

/** Parses `raw` per `format`, returning an ISO "YYYY-MM-DD" string, or null
 * if it doesn't match the pattern or isn't a real calendar date (e.g. Feb 30
 * round-trips to Mar 2, which this catches by re-checking the parts). */
export function parseDateWithFormat(raw: string, format: DateFormat): string | null {
  const { regex, order } = DATE_PATTERNS[format];
  const match = raw.trim().match(regex);
  if (!match) return null;

  const parts: Record<"y" | "m" | "d", number> = { y: 0, m: 0, d: 0 };
  order.forEach((key, index) => {
    parts[key] = Number(match[index + 1]);
  });
  const { y: year, m: month, d: day } = parts;
  if (month < 1 || month > 12 || day < 1 || day > 31) return null;

  const date = new Date(year, month - 1, day);
  if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) return null;

  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

/** Parses a bank-export amount string — handles thousands separators and
 * either "," or "." as the decimal mark by assuming whichever comes last is
 * the decimal separator (e.g. "1.234,56" and "1,234.56" both work). */
export function parseAmount(raw: string): number | null {
  let value = raw.trim().replace(/[\s ]/g, "");
  if (!value) return null;

  const hasComma = value.includes(",");
  const hasDot = value.includes(".");
  if (hasComma && hasDot) {
    value = value.lastIndexOf(",") > value.lastIndexOf(".") ? value.replace(/\./g, "").replace(",", ".") : value.replace(/,/g, "");
  } else if (hasComma) {
    value = value.replace(",", ".");
  }

  const num = Number(value);
  return Number.isFinite(num) ? num : null;
}

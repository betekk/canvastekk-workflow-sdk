#!/usr/bin/env node
// canvastekk-workflow-sdk skill installer — lean add/list for the bundled
// agent skills, versioned against SDK release tags. Installs from the
// CI-guarded .agents/skills mirror (kept byte-identical with the wheel's
// data/skills by the skill-mirror-guard CI job).
// Usage:
//   npx github:betekk/canvastekk-workflow-sdk list
//   npx github:betekk/canvastekk-workflow-sdk list installed      # project scope; --global for user scope
//   npx github:betekk/canvastekk-workflow-sdk add <skill>         # project scope (./.agents/skills) — ecosystem default
//   npx github:betekk/canvastekk-workflow-sdk add <skill> -g      # user scope (~/.agents/skills)
//   npx github:betekk/canvastekk-workflow-sdk#v0.52.5 add <skill> # pinned — rollback = older tag
//   npx github:betekk/canvastekk-workflow-sdk add <skill> --ref main        # unreleased tree
//   npx github:betekk/canvastekk-workflow-sdk add <skill> --project <dir>   # explicit project dir
//   npx github:betekk/canvastekk-workflow-sdk add <skill> --dry-run         # print targets, write nothing
import { cp, readdir, readFile, writeFile, mkdir, rm, mkdtemp } from "node:fs/promises";
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import os from "node:os";

const REPO = dirname(dirname(fileURLToPath(import.meta.url)));
const SKILLS_SRC = join(REPO, ".agents", "skills");
const SIDECAR = ".skill-source.json";
// Install provenance ({source, ref, version}) — resolved by the version
// router in main(); defaulted to the running tree when unset.
let installSource = null;

function repoUrl() {
  // The npx-fetched tree has no .git — package.json is the stable source.
  const pkg = JSON.parse(readFileSync(join(REPO, "package.json"), "utf8"));
  const url = (pkg.repository && (typeof pkg.repository === "string" ? pkg.repository : pkg.repository.url)) || "";
  if (!url) { console.error("error: package.json has no repository field — cannot resolve release refs"); process.exit(2); }
  return url.replace(/^git\+/, "").replace(/^git@github\.com:/, "https://github.com/");
}
function shortSource(url) { return url.replace(/^https:\/\/github\.com\//, "github:").replace(/\.git$/, ""); }
async function treeVersion() {
  // The SDK version in python/pyproject.toml [project] doubles as the skill
  // version — skills ride SDK releases, no separate VERSION file.
  const toml = await readFile(join(REPO, "python", "pyproject.toml"), "utf8");
  const m = toml.match(/^version\s*=\s*"([^"]+)"/m);
  if (!m) throw new Error("python/pyproject.toml has no version field");
  return m[1].trim();
}
function semverKey(v) { const [, a, b, c] = v.match(/^v(\d+)\.(\d+)\.(\d+)$/) || []; return a ? [+a, +b, +c] : null; }
function parseTagLines(out) {
  // ls-remote --tags output → highest vX.Y.Z (peeled `^{}` lines dropped).
  const tags = out.split("\n")
    .map((l) => (l.split("\t")[1] || "").trim())
    .filter((t) => /^refs\/tags\/v\d+\.\d+\.\d+$/.test(t))
    .map((t) => t.replace("refs\/tags\/", ""));
  const valid = tags.filter((t) => semverKey(t));
  valid.sort((x, y) => { const a = semverKey(x), b = semverKey(y); return a[0] - b[0] || a[1] - b[1] || a[2] - b[2]; });
  return valid.at(-1) || null;
}
function resolveLatestTag(url) {
  const r = spawnSync("git", ["ls-remote", "--tags", url], { encoding: "utf8", maxBuffer: 16 * 1024 * 1024 });
  if (r.error || r.status !== 0) throw new Error(`git ls-remote --tags ${url} failed: ${(r.stderr || r.error || "").toString().trim()}`);
  return parseTagLines(r.stdout);
}
async function skillSourceMeta() {
  if (installSource) return installSource;
  const version = await treeVersion();
  return { source: shortSource(repoUrl()), ref: `v${version}`, version };
}
function listSkillFiles(dir) {
  const files = [];
  const walk = (d, prefix) => {
    for (const e of readdirSync(d, { withFileTypes: true })) {
      const rel = prefix ? `${prefix}/${e.name}` : e.name;
      if (e.isDirectory()) walk(join(d, e.name), rel);
      else files.push(rel);
    }
  };
  walk(dir, "");
  return files.sort();
}
async function writeSkillSidecar(dst) {
  const meta = await skillSourceMeta();
  await writeFile(join(dst, SIDECAR), JSON.stringify({ ...meta, installedAt: new Date().toISOString(), files: listSkillFiles(dst) }, null, 2) + "\n", "utf8");
}

async function listSkills() {
  const out = [];
  for (const dir of await readdir(SKILLS_SRC)) {
    const sf = join(SKILLS_SRC, dir, "SKILL.md");
    if (!existsSync(sf)) continue;
    const fm = (await readFile(sf, "utf8")).split("---")[1] || "";
    const name = (fm.match(/^name:\s*(.+)$/m) || [])[1]?.trim() || dir;
    let desc = "";
    const dm = fm.match(/^description:\s*>-?\s*\n([\s\S]*?)\n\w|^description:\s*(.+)$/m);
    if (dm) {
      desc = (dm[1] || dm[2] || "").replace(/\n\s+/g, " ").trim();
    }
    out.push({ name, dir, description: desc });
  }
  return out;
}

function userSkillsDir() { return join(os.homedir(), ".agents", "skills"); }

// Scope resolution (ecosystem convention: project default, -g opts into user
// scope — mirrors `npx skills add`): explicit --project dir > --global > cwd.
function resolveTargetDir({ projectDir, globalFlag }) {
  if (projectDir) return join(projectDir, ".agents", "skills");
  if (globalFlag) return userSkillsDir();
  return join(process.cwd(), ".agents", "skills");
}

async function listInstalled({ globalFlag }) {
  // installed-vs-latest per skill, from the sidecar stamp (one ls-remote).
  const target = resolveTargetDir({ projectDir: null, globalFlag });
  const scope = globalFlag ? "user" : "project";
  let latest = null;
  try { latest = resolveLatestTag(repoUrl()); } catch (e) { console.error(`note: latest-tag lookup failed (${e.message.split("\n")[0]})`); }
  if (!existsSync(target)) { console.log(`no skills installed (${scope} scope).`); return; }
  const rows = [];
  for (const dir of await readdir(target)) {
    const sc = join(target, dir, SIDECAR);
    if (!existsSync(sc)) continue;
    const m = JSON.parse(await readFile(sc, "utf8"));
    const norm = String(m.version || "").replace(/^v/, "");
    rows.push({ name: m.name || dir, installedRef: m.ref, installedVersion: m.version, latest: latest || null, updateAvailable: !!(latest && norm && latest !== `v${norm}`) });
  }
  rows.sort((a, b) => a.name.localeCompare(b.name));
  if (!rows.length) { console.log(`no stamped skills installed (${scope} scope).`); return; }
  console.log(`installed skills (${scope} scope) vs latest release:\n`);
  for (const r of rows) {
    const flag = r.updateAvailable ? "  <- update available (re-run add)" : "";
    console.log(`  ${r.name.padEnd(38)} ${String(r.installedRef || "?").padEnd(12)} latest: ${r.latest || "?"}${flag}`);
  }
}

function takeFlag(rest, flag) {
  const i = rest.indexOf(flag);
  if (i === -1) return null;
  const v = rest[i + 1];
  return v === undefined ? "." : v;
}

async function main() {
  const [, , cmd, name, ...rest] = process.argv;
  const source = takeFlag(rest, "--source");
  const ref = takeFlag(rest, "--ref");
  const projectFlag = rest.includes("--project");
  const projectDir = projectFlag ? resolve(rest[rest.indexOf("--project") + 1] || ".") : null;
  const globalFlag = rest.includes("-g") || rest.includes("--global");
  const dryRun = rest.includes("--dry-run");

  if (cmd === "list" && name === "installed") { await listInstalled({ globalFlag }); return; }

  if (cmd === "list" || !cmd) {
    const skills = await listSkills();
    console.log("canvastekk-workflow-sdk bundled skills:\n");
    for (const s of skills) console.log(`  ${s.name.padEnd(38)} ${s.description.slice(0, 90)}`);
    console.log(`\ninstall: npx github:betekk/canvastekk-workflow-sdk add <name>   # project scope`);
    console.log(`user scope: npx github:betekk/canvastekk-workflow-sdk add <name> -g`);
    console.log(`versions: npx github:betekk/canvastekk-workflow-sdk list installed`);
    return;
  }

  // Version router: `add` installs from the LATEST release tag by default.
  // Tree already at that release → proceed locally; otherwise shallow-clone
  // the wanted ref and re-exec this installer from that tree (same version
  // as the installed content). --ref overrides; --source installs from the
  // running tree (dev mode, no fetch); --dry-run skips the router (read-only
  // run reports the running tree).
  if (cmd === "add" && !source && !dryRun) {
    const url = repoUrl();
    const local = await treeVersion();
    let wanted = ref;
    if (!wanted) {
      try { wanted = resolveLatestTag(url); } catch (e) {
        console.error(`error: cannot resolve the latest release tag (${e.message.split("\n")[0]}). Pass --ref <tag|main> explicitly, or --source . to install from the running tree.`);
        process.exit(2);
      }
    }
    if (!wanted) { console.error("error: no release tags found — pass --ref main or --source ."); process.exit(2); }
    if (wanted === `v${local}`) {
      installSource = { source: shortSource(url), ref: wanted, version: local };
    } else {
      const tmp = await mkdtemp(join(os.tmpdir(), "ctw-sdk-skills-"));
      console.error(`fetching ${wanted} (running tree: v${local})…`);
      const clone = spawnSync("git", ["clone", "--depth", "1", "--branch", wanted, url, tmp], { stdio: ["ignore", "ignore", "inherit"] });
      if (clone.status !== 0) { await rm(tmp, { recursive: true, force: true }); console.error(`error: clone of ${wanted} failed — check the ref name and network access, or use --source . to install from the running tree`); process.exit(2); }
      const r = spawnSync(process.execPath, [join(tmp, "installer", "init.mjs"), ...process.argv.slice(2), "--source", tmp], { stdio: "inherit" });
      await rm(tmp, { recursive: true, force: true });
      if ((r.status ?? 1) !== 0) process.exit(r.status ?? 1);
      // Stamp the requested skill's dir if the inner left it unstamped
      // (idempotent: new inners already wrote it).
      const dest = join(resolveTargetDir({ projectDir, globalFlag }), name);
      if (name && !existsSync(join(dest, SIDECAR))) await writeSkillSidecar(dest);
      process.exit(0);
    }
  } else if (source && cmd === "add") {
    const version = await treeVersion();
    installSource = { source: shortSource(repoUrl()), ref: ref || `v${version}`, version };
  }

  if (cmd === "add") {
    if (!name) { console.error("usage: add <skill-name> [-g | --project <dir>] [--ref <tag|main>] [--source .] [--dry-run]"); process.exit(1); }
    if (/[\\/]/.test(name) || name.includes("..")) { console.error(`error: invalid skill name: ${name}`); process.exit(1); }
    const src = join(SKILLS_SRC, name);
    if (!existsSync(join(src, "SKILL.md"))) {
      const skills = await listSkills();
      console.error(`skill not found: ${name}\navailable: ${skills.map((s) => s.name).join(", ")}`);
      process.exit(1);
    }
    const target = resolveTargetDir({ projectDir, globalFlag });
    const dest = join(target, name);
    if (dryRun) {
      const meta = await skillSourceMeta();
      console.log(`dry-run: would copy ${name} -> ${dest}`);
      console.log(`dry-run: would write ${join(dest, SIDECAR)} (version ${meta.version}, ref ${meta.ref})`);
      console.log("dry-run: nothing written.");
      return;
    }
    await mkdir(dirname(dest), { recursive: true });
    await cp(src, dest, { recursive: true });
    await writeSkillSidecar(dest);
    console.log(`installed ${name} -> ${dest}`);
    console.log("restart your agent (opencode/claude/pi) to pick it up.");
    return;
  }
  console.error(`unknown command: ${cmd}\nusage: list | list installed [--global] | add <skill> [-g | --project <dir>] [--ref <tag|main>] [--source .] [--dry-run]`);
  process.exit(1);
}

main().catch(e => { console.error(e); process.exit(1); });

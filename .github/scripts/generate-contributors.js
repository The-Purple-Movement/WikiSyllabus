// Required deps: js-yaml, node-fetch@2, gray-matter, fs, path, glob
const fs = require("fs");
const path = require("path");
const yaml = require("js-yaml");
const matter = require("gray-matter");
const fetch = require("node-fetch");
const glob = require("glob");

const token = process.env.GITHUB_TOKEN;
const repo = process.env.REPO; // e.g. "owner/repo"

if (!token || !repo) {
  console.error("❌ Missing GITHUB_TOKEN or REPO in env vars");
  process.exit(1);
}

// Fetch repo contributors from GitHub API
async function fetchRepoContributors() {
  let contributors = [];
  let page = 1;

  while (true) {
    const res = await fetch(
      `https://api.github.com/repos/${repo}/contributors?per_page=100&page=${page}`,
      {
        headers: { Authorization: `token ${token}` },
      }
    );
    if (!res.ok) {
      console.error(`❌ GitHub API error: ${res.status} ${res.statusText}`);
      process.exit(1);
    }

    const data = await res.json();
    if (data.length === 0) break;

    contributors.push(...data.map((c) => c.login));
    page++;
  }

  return contributors;
}

// Extract contributors from YAML front matter of all .md files
function fetchMdContributors() {
  const files = glob.sync("**/*.md", {
    ignore: ["node_modules/**", "CONTRIBUTORS.md"],
  });

  let allMdContributors = [];

  for (const file of files) {
    const content = fs.readFileSync(file, "utf8");
    const parsed = matter(content);

    if (parsed.data && parsed.data.contributors) {
      const contributors = Array.isArray(parsed.data.contributors)
        ? parsed.data.contributors
        : [parsed.data.contributors];

      allMdContributors.push(...contributors.map((c) => String(c).trim()));
    }
  }

  return allMdContributors;
}

// Get avatar + profile URL for each contributor
async function fetchContributorDetails(usernames) {
  const details = [];

  for (const username of usernames) {
    const res = await fetch(`https://api.github.com/users/${username}`, {
      headers: { Authorization: `token ${token}` },
    });

    if (!res.ok) {
      console.warn(`⚠️ Could not fetch details for ${username}`);
      continue;
    }

    const data = await res.json();
    details.push({
      login: data.login,
      avatar_url: data.avatar_url,
      html_url: data.html_url,
    });
  }

  return details;
}

// Generate CONTRIBUTORS.md
function generateMarkdown(contributors) {
  let md = `# 🏆 Contributors\n\nThanks to all the amazing people who contributed to this project!\n\n`;

  // Avatar grid
  md += contributors
    .map(
      (c) =>
        `[<img src="${c.avatar_url}&s=64" width="64" height="64" alt="${c.login}"/>](${c.html_url})`
    )
    .join(" ");

  md += `\n\n---\nGenerated automatically by a [GitHub Action](.github/workflows/contributors.yml).\n`;

  return md;
}

(async () => {
  console.log("📦 Fetching repo contributors...");
  const repoContribs = await fetchRepoContributors();

  console.log("📄 Fetching MD file contributors...");
  const mdContribs = fetchMdContributors();

  // Merge + deduplicate
  const allContribs = Array.from(
    new Set([...repoContribs, ...mdContribs].map((u) => u.trim()))
  );

  console.log(`✅ Found ${allContribs.length} unique contributors`);

  console.log("🖼 Fetching contributor profile details...");
  const details = await fetchContributorDetails(allContribs);

  console.log("📝 Generating CONTRIBUTORS.md...");
  const md = generateMarkdown(details);

  fs.writeFileSync("CONTRIBUTORS.md", md, "utf8");
  console.log("🎉 CONTRIBUTORS.md updated!");
})();

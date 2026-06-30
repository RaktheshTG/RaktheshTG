#!/usr/bin/env node
// scripts/generate-stats.js
// Fetches the contribution calendar using GitHub GraphQL and generates assets/stats-card.svg

const fs = require('fs');
const path = require('path');
const fetch = globalThis.fetch;

const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
const GITHUB_USER = process.env.GITHUB_USER;
const TARGET_STREAK = process.env.TARGET_STREAK ? Number(process.env.TARGET_STREAK) : null;

const MOCK_MODE = (!GITHUB_TOKEN || !GITHUB_USER);

if (MOCK_MODE) {
	console.warn('GITHUB_TOKEN or GITHUB_USER missing — running in MOCK mode and generating sample SVG.');
}

const GRAPHQL = `
query contribs($login: String!) {
	user(login: $login) {
		contributionsCollection {
			contributionCalendar {
				totalContributions
				weeks {
					contributionDays {
						date
						contributionCount
					}
				}
			}
		}
	}
}
`;

async function fetchContributions(login) {
	const res = await fetch('https://api.github.com/graphql', {
		method: 'POST',
		headers: {
			'Content-Type': 'application/json',
			Authorization: `Bearer ${GITHUB_TOKEN}`,
		},
		body: JSON.stringify({ query: GRAPHQL, variables: { login } }),
	});
	if (!res.ok) {
		const txt = await res.text();
		throw new Error(`GitHub API error ${res.status}: ${txt}`);
	}
	const data = await res.json();
	return data.data.user.contributionsCollection.contributionCalendar;
}

function flattenDays(weeks) {
	const days = [];
	for (const w of weeks) {
		for (const d of w.contributionDays) days.push(d);
	}
	// sort by date ascending
	days.sort((a, b) => new Date(a.date) - new Date(b.date));
	return days;
}

function computeStreaks(days) {
	// days is sorted ascending (oldest -> newest)
	let longest = 0;
	let running = 0;
	for (let i = 0; i < days.length; i++) {
		if (days[i].contributionCount > 0) {
			running += 1;
			if (running > longest) longest = running;
		} else {
			running = 0;
		}
	}

	// compute current streak: if today's count is 0, do not include today — count trailing positive days
	let current = 0;
	let i = days.length - 1;
	if (i >= 0 && days[i].contributionCount === 0) {
		// skip today's zero
		i -= 1;
	}
	while (i >= 0 && days[i].contributionCount > 0) {
		current += 1;
		i -= 1;
	}

	return { current, longest };
}

function buildSvg(template, replacements) {
	let out = template;
	for (const k of Object.keys(replacements)) {
		out = out.replace(new RegExp(`{{${k}}}`, 'g'), String(replacements[k]));
	}
	return out;
}

async function main() {
	const templatePath = path.resolve(__dirname, '..', 'assets', 'stats-template.svg');
	const outPath = path.resolve(__dirname, '..', 'assets', 'stats-card.svg');
	const template = fs.readFileSync(templatePath, 'utf8');

	let total = 0;
	let current = 0;
	let longest = 0;

	if (MOCK_MODE) {
		// Provide deterministic mock data so the user can preview output without tokens
		total = 1234;
		current = 7;
		longest = 42;
	} else {
		const calendar = await fetchContributions(GITHUB_USER);
		total = calendar.totalContributions || 0;
		const days = flattenDays(calendar.weeks || []);
		({ current, longest } = computeStreaks(days));
	}

	const target = TARGET_STREAK || longest || 1;
	const percent = Math.round((current / target) * 100);

	// ring math: radius 90 -> circumference
	const r = 90;
	const circumference = 2 * Math.PI * r; // ~565.4867
	const dash = Math.round((percent / 100) * circumference * 1000) / 1000; // keep precision
	const ringDash = `${dash} ${Math.round(circumference * 1000) / 1000}`;

	const replacements = {
		TOTAL: total,
		CURRENT: current,
		LONGEST: longest,
		PERCENT: percent,
		RING_DASH: ringDash,
	};

	const outSvg = buildSvg(template, replacements);
	fs.writeFileSync(outPath, outSvg, 'utf8');
	console.log('Wrote', outPath, { total, current, longest, percent, mock: MOCK_MODE });
}

main().catch(err => {
	console.error(err);
	process.exit(1);
});


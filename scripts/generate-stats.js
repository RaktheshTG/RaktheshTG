#!/usr/bin/env node

const fs = require('fs');
const path = require('path');

const GRAPHQL = `
query ContributionStats($login: String!) {
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

function flattenDays(weeks) {
  return weeks
    .flatMap((week) => week.contributionDays)
    .sort((a, b) => a.date.localeCompare(b.date));
}

function previousDate(date) {
  const value = new Date(`${date}T00:00:00Z`);
  value.setUTCDate(value.getUTCDate() - 1);
  return value.toISOString().slice(0, 10);
}

function computeStreaks(days, today = new Date().toISOString().slice(0, 10)) {
  const completedDays = days.filter((day) => day.date <= today);
  const counts = new Map(
    completedDays.map((day) => [day.date, Number(day.contributionCount) || 0]),
  );

  let longest = 0;
  let running = 0;
  let activeDays = 0;

  for (const day of completedDays) {
    if (day.contributionCount > 0) {
      activeDays += 1;
      running += 1;
      longest = Math.max(longest, running);
    } else {
      running = 0;
    }
  }

  let cursor = counts.get(today) > 0 ? today : previousDate(today);
  let current = 0;

  while ((counts.get(cursor) || 0) > 0) {
    current += 1;
    cursor = previousDate(cursor);
  }

  return { current, longest, activeDays };
}

async function fetchContributions(login, token) {
  const response = await fetch('https://api.github.com/graphql', {
    method: 'POST',
    headers: {
      Accept: 'application/vnd.github+json',
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      'User-Agent': 'profile-stats-generator',
      'X-GitHub-Api-Version': '2022-11-28',
    },
    body: JSON.stringify({ query: GRAPHQL, variables: { login } }),
  });

  if (!response.ok) {
    throw new Error(`GitHub API returned ${response.status}: ${await response.text()}`);
  }

  const payload = await response.json();
  if (payload.errors?.length) {
    throw new Error(`GitHub GraphQL error: ${payload.errors.map((error) => error.message).join('; ')}`);
  }

  const calendar = payload.data?.user?.contributionsCollection?.contributionCalendar;
  if (!calendar) {
    throw new Error(`GitHub user "${login}" was not found or returned no contribution calendar`);
  }

  return calendar;
}

function buildSvg(template, replacements) {
  return Object.entries(replacements).reduce(
    (svg, [key, value]) => svg.replaceAll(`{{${key}}}`, String(value)),
    template,
  );
}

async function main() {
  const token = process.env.GITHUB_TOKEN;
  const user = process.env.GITHUB_USER;

  if (!token || !user) {
    throw new Error('GITHUB_TOKEN and GITHUB_USER are required; refusing to generate fake stats');
  }

  const calendar = await fetchContributions(user, token);
  const days = flattenDays(calendar.weeks || []);
  const { current, longest, activeDays } = computeStreaks(days);
  const target = Math.max(Number(process.env.TARGET_STREAK) || 30, 1);
  const percent = Math.min(Math.round((current / target) * 100), 100);
  const circumference = 2 * Math.PI * 64;
  const ringLength = (percent / 100) * circumference;

  const replacements = {
    TOTAL: calendar.totalContributions || 0,
    CURRENT: current,
    LONGEST: longest,
    ACTIVE_DAYS: activeDays,
    PERCENT: percent,
    RING_DASH: `${ringLength.toFixed(3)} ${circumference.toFixed(3)}`,
    BAR_WIDTH: ((percent / 100) * 634).toFixed(1),
    UPDATED: new Date().toISOString().slice(0, 10),
  };

  const variants = [
    { template: 'stats-template.svg', output: 'stats-card.svg' },
    { template: 'stats-template-light.svg', output: 'stats-card-light.svg' },
  ];

  for (const { template: templateName, output: outputName } of variants) {
    const templatePath = path.resolve(__dirname, '..', 'assets', templateName);
    const outputPath = path.resolve(__dirname, '..', 'assets', outputName);
    const template = fs.readFileSync(templatePath, 'utf8');
    fs.writeFileSync(outputPath, buildSvg(template, replacements), 'utf8');
    console.log(`Updated ${path.relative(process.cwd(), outputPath)} for @${user}`);
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(error.message);
    process.exitCode = 1;
  });
}

module.exports = { buildSvg, computeStreaks, flattenDays, previousDate };

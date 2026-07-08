#!/usr/bin/env python3
"""
Generate colorful analytics SVGs showing:
1. Language distribution by commit count
2. Top repositories by commit count
Updated daily via GitHub Actions and regenerated on each push.
"""

import os
from github import Github

# Initialize GitHub client
gh = Github(os.getenv("GITHUB_TOKEN"))
user = gh.get_user("RaktheshTG")

# Get all repos and calculate language distribution
language_commits = {}
repo_commits = {}
all_repos = user.get_repos(sort="updated", direction="desc")

for repo in all_repos:
    if repo.fork or repo.archived:
        continue
    
    try:
        # Get language breakdown
        languages = repo.get_languages()
        commits = repo.get_commits().totalCount
        
        repo_commits[repo.name] = commits
        
        # Aggregate languages by commit count (approximate by language bytes ratio)
        for lang, bytes_count in languages.items():
            language_commits[lang] = language_commits.get(lang, 0) + (bytes_count // 1000)
    except:
        pass

# Sort and get top 6 languages
sorted_languages = sorted(language_commits.items(), key=lambda x: x[1], reverse=True)[:6]
total_lang_count = sum(count for _, count in sorted_languages)

# Sort and get top 5 repos
sorted_repos = sorted(repo_commits.items(), key=lambda x: x[1], reverse=True)[:5]

# Color mappings
language_colors = {
    "Python": {"start": "#1E90FF", "end": "#87CEEB"},
    "JavaScript": {"start": "#FFD700", "end": "#FFA500"},
    "TypeScript": {"start": "#3178C6", "end": "#61DAFB"},
    "C++": {"start": "#FF1744", "end": "#FF6B9D"},
    "Java": {"start": "#ED8B00", "end": "#FFB84D"},
    "CSS": {"start": "#254BDD", "end": "#FF7F50"},
    "HTML": {"start": "#E34F26", "end": "#FF7F50"},
    "SQL": {"start": "#00A4A4", "end": "#00D4D4"},
}

repo_color_order = ["#1E90FF", "#FFD700", "#3178C6", "#FF1744", "#ED8B00"]

def get_color(key, index=0):
    """Get color for a language or repo"""
    if key in language_colors:
        return language_colors[key]["start"]
    return repo_color_order[index % len(repo_color_order)]

def generate_dark_svg():
    """Generate dark theme analytics SVG"""
    svg_lines = [
        '<svg width="100%" height="500" viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg">',
        '  <defs>',
        '    <linearGradient id="bgGradientDark" x1="0%" y1="0%" x2="100%" y2="100%">',
        '      <stop offset="0%" style="stop-color:#1a0f3f;stop-opacity:1" />',
        '      <stop offset="50%" style="stop-color:#2d1b69;stop-opacity:1" />',
        '      <stop offset="100%" style="stop-color:#1a0f3f;stop-opacity:1" />',
        '    </linearGradient>',
    ]
    
    # Add color gradients for each language
    for i, (lang, _) in enumerate(sorted_languages):
        color = get_color(lang, i)
        svg_lines.append(f'    <linearGradient id="lang{i}" x1="0%" y1="0%" x2="100%" y2="0%">')
        svg_lines.append(f'      <stop offset="0%" style="stop-color:{color};stop-opacity:1" />')
        svg_lines.append(f'      <stop offset="100%" style="stop-color:#A78BFA;stop-opacity:0.8" />')
        svg_lines.append('    </linearGradient>')
    
    svg_lines.extend([
        '    <filter id="glowDark">',
        '      <feGaussianBlur stdDeviation="3" result="coloredBlur"/>',
        '      <feMerge>',
        '        <feMergeNode in="coloredBlur"/>',
        '        <feMergeNode in="SourceGraphic"/>',
        '      </feMerge>',
        '    </filter>',
        '  </defs>',
        '  ',
        '  <!-- Background -->',
        '  <rect width="1000" height="500" fill="url(#bgGradientDark)" rx="12"/>',
        '  ',
        '  <!-- Left Column: Language Distribution -->',
        '  <text x="40" y="40" font-size="24" font-weight="bold" fill="#E0E7FF">📊 Language Distribution</text>',
    ])
    
    # Add language bars
    y_pos = 80
    for i, (lang, count) in enumerate(sorted_languages):
        percentage = (count / total_lang_count) * 100 if total_lang_count > 0 else 0
        bar_width = (percentage / 100) * 280
        
        svg_lines.append(f'  <rect x="40" y="{y_pos}" width="{bar_width}" height="45" fill="url(#lang{i})" rx="6" filter="url(#glowDark)" opacity="0.9"/>')
        svg_lines.append(f'  <text x="60" y="{y_pos + 32}" font-size="14" fill="#FFFFFF" font-weight="bold">{lang}</text>')
        svg_lines.append(f'  <text x="330" y="{y_pos + 32}" font-size="14" fill="#A78BFA" font-weight="bold">{percentage:.0f}%</text>')
        y_pos += 55
    
    # Vertical divider
    svg_lines.append('  <line x1="550" y1="30" x2="550" y2="480" stroke="#8B7CFF" stroke-width="2" opacity="0.3"/>')
    
    # Right Column: Top Repositories
    svg_lines.append('  <text x="600" y="40" font-size="24" font-weight="bold" fill="#E0E7FF">🔥 Top Repositories</text>')
    
    y_pos = 85
    for i, (repo_name, commits) in enumerate(sorted_repos):
        color = get_color("", i)
        radius = 30 - (i * 3)
        
        svg_lines.append(f'  <circle cx="630" cy="{y_pos}" r="{radius}" fill="{color}" filter="url(#glowDark)" opacity="0.85"/>')
        svg_lines.append(f'  <text x="630" y="{y_pos + 5}" font-size="16" fill="#FFFFFF" font-weight="bold" text-anchor="middle">{commits}</text>')
        svg_lines.append(f'  <text x="690" y="{y_pos - 5}" font-size="13" fill="#E0E7FF" font-weight="600">{repo_name}</text>')
        svg_lines.append(f'  <text x="690" y="{y_pos + 12}" font-size="11" fill="#A78BFA">{commits} commits</text>')
        y_pos += 65
    
    svg_lines.append('</svg>')
    return '\n'.join(svg_lines)

def generate_light_svg():
    """Generate light theme analytics SVG"""
    svg_lines = [
        '<svg width="100%" height="500" viewBox="0 0 1000 500" xmlns="http://www.w3.org/2000/svg">',
        '  <defs>',
        '    <linearGradient id="bgGradientLight" x1="0%" y1="0%" x2="100%" y2="100%">',
        '      <stop offset="0%" style="stop-color:#f0e7ff;stop-opacity:1" />',
        '      <stop offset="50%" style="stop-color:#e9d5ff;stop-opacity:1" />',
        '      <stop offset="100%" style="stop-color:#ddd6fe;stop-opacity:1" />',
        '    </linearGradient>',
    ]
    
    # Add color gradients for each language
    for i, (lang, _) in enumerate(sorted_languages):
        color = get_color(lang, i)
        svg_lines.append(f'    <linearGradient id="langLight{i}" x1="0%" y1="0%" x2="100%" y2="0%">')
        svg_lines.append(f'      <stop offset="0%" style="stop-color:{color};stop-opacity:1" />')
        svg_lines.append(f'      <stop offset="100%" style="stop-color:#C4B5FD;stop-opacity:0.8" />')
        svg_lines.append('    </linearGradient>')
    
    svg_lines.extend([
        '    <filter id="glowLight">',
        '      <feGaussianBlur stdDeviation="2" result="coloredBlur"/>',
        '      <feMerge>',
        '        <feMergeNode in="coloredBlur"/>',
        '        <feMergeNode in="SourceGraphic"/>',
        '      </feMerge>',
        '    </filter>',
        '  </defs>',
        '  ',
        '  <!-- Background -->',
        '  <rect width="1000" height="500" fill="url(#bgGradientLight)" rx="12"/>',
        '  ',
        '  <!-- Left Column: Language Distribution -->',
        '  <text x="40" y="40" font-size="24" font-weight="bold" fill="#5B21B6">📊 Language Distribution</text>',
    ])
    
    # Add language bars
    y_pos = 80
    for i, (lang, count) in enumerate(sorted_languages):
        percentage = (count / total_lang_count) * 100 if total_lang_count > 0 else 0
        bar_width = (percentage / 100) * 280
        
        svg_lines.append(f'  <rect x="40" y="{y_pos}" width="{bar_width}" height="45" fill="url(#langLight{i})" rx="6" filter="url(#glowLight)" opacity="0.85"/>')
        svg_lines.append(f'  <text x="60" y="{y_pos + 32}" font-size="14" fill="#1F1F1F" font-weight="bold">{lang}</text>')
        svg_lines.append(f'  <text x="330" y="{y_pos + 32}" font-size="14" fill="#6B21B6" font-weight="bold">{percentage:.0f}%</text>')
        y_pos += 55
    
    # Vertical divider
    svg_lines.append('  <line x1="550" y1="30" x2="550" y2="480" stroke="#A78BFA" stroke-width="2" opacity="0.3"/>')
    
    # Right Column: Top Repositories
    svg_lines.append('  <text x="600" y="40" font-size="24" font-weight="bold" fill="#5B21B6">🔥 Top Repositories</text>')
    
    y_pos = 85
    for i, (repo_name, commits) in enumerate(sorted_repos):
        color = get_color("", i)
        radius = 30 - (i * 3)
        
        svg_lines.append(f'  <circle cx="630" cy="{y_pos}" r="{radius}" fill="{color}" filter="url(#glowLight)" opacity="0.75"/>')
        svg_lines.append(f'  <text x="630" y="{y_pos + 5}" font-size="16" fill="#FFFFFF" font-weight="bold" text-anchor="middle">{commits}</text>')
        svg_lines.append(f'  <text x="690" y="{y_pos - 5}" font-size="13" fill="#5B21B6" font-weight="600">{repo_name}</text>')
        svg_lines.append(f'  <text x="690" y="{y_pos + 12}" font-size="11" fill="#7C3AED">{commits} commits</text>')
        y_pos += 65
    
    svg_lines.append('</svg>')
    return '\n'.join(svg_lines)

# Generate and save SVGs
os.makedirs("assets", exist_ok=True)

dark_svg = generate_dark_svg()
with open("assets/analytics-dark.svg", "w") as f:
    f.write(dark_svg)

light_svg = generate_light_svg()
with open("assets/analytics-light.svg", "w") as f:
    f.write(light_svg)

print("✅ Analytics SVGs generated successfully!")
print(f"Languages: {[lang for lang, _ in sorted_languages]}")
print(f"Top repos: {[repo for repo, _ in sorted_repos]}")

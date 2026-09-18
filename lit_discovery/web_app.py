"""FastAPI Web Application for LitDiscovery: Interactive research intelligence UI."""
import os
import tempfile
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from pydantic import BaseModel

from lit_discovery.core.dispatcher import search_literature, AVAILABLE_ENGINES
from lit_discovery.intelligence.citation_graph import explore_citation_graph
from lit_discovery.synthesis.deep_reader import deep_read_pdf
from lit_discovery.exports.zotero import export_zotero_references

app = FastAPI(
    title="LitDiscovery Web UI",
    description="Interactive literature discovery, smart citation consensus, and paper synthesis application.",
    version="1.0.0"
)

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en" class="h-full bg-slate-950 text-slate-100">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LitDiscovery — Scientific Research Intelligence</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: {
              50: '#f0fdf4',
              500: '#22c55e',
              600: '#16a34a',
              700: '#15803d',
              900: '#14532d',
            }
          }
        }
      }
    }
  </script>
  <style>
    ::-webkit-scrollbar { width: 8px; height: 8px; }
    ::-webkit-scrollbar-track { background: #0f172a; }
    ::-webkit-scrollbar-thumb { background: #334155; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #475569; }
  </style>
</head>
<body class="min-h-full flex flex-col font-sans antialiased selection:bg-emerald-500 selection:text-black">

  <!-- Navigation Bar -->
  <header class="border-b border-slate-800 bg-slate-900/80 backdrop-blur sticky top-0 z-50">
    <div class="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-16 flex items-center justify-between">
      <div class="flex items-center space-x-3">
        <div class="w-10 h-10 rounded-xl bg-gradient-to-tr from-emerald-500 to-teal-400 flex items-center justify-center shadow-lg shadow-emerald-500/20">
          <i class="fa-solid fa-atom text-slate-950 text-xl font-black"></i>
        </div>
        <div>
          <span class="font-extrabold text-xl tracking-tight text-white flex items-center gap-2">
            Lit<span class="text-emerald-400">Discovery</span>
            <span class="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">v1.0.0</span>
          </span>
          <p class="text-xs text-slate-400 hidden sm:block">Open-Source Research Intelligence & Smart Citation Discovery</p>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <span class="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700">
          <span class="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
          12 Search Engines Online
        </span>
        <a href="https://github.com/" target="_blank" class="text-slate-400 hover:text-white transition-colors p-2 text-lg">
          <i class="fa-brands fa-github"></i>
        </a>
      </div>
    </div>
  </header>

  <!-- Main Container -->
  <main class="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-8 flex flex-col gap-6">

    <!-- Tab Selector -->
    <div class="flex border-b border-slate-800 gap-4 text-sm font-semibold">
      <button id="tab-search-btn" onclick="switchTab('search')" class="pb-3 border-b-2 border-emerald-500 text-emerald-400 flex items-center gap-2">
        <i class="fa-solid fa-magnifying-glass"></i> Literature Discovery & Synthesis
      </button>
      <button id="tab-graph-btn" onclick="switchTab('graph')" class="pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2">
        <i class="fa-solid fa-diagram-project"></i> Citation Graph Snowballing
      </button>
      <button id="tab-reader-btn" onclick="switchTab('reader')" class="pb-3 border-b-2 border-transparent text-slate-400 hover:text-slate-200 flex items-center gap-2">
        <i class="fa-solid fa-file-pdf"></i> PyMuPDF Deep Reader
      </button>
    </div>

    <!-- TAB 1: LITERATURE DISCOVERY -->
    <section id="tab-search" class="flex flex-col gap-6">
      <!-- Search Input Card -->
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl relative overflow-hidden">
        <div class="absolute -right-20 -top-20 w-64 h-64 bg-emerald-500/5 rounded-full blur-3xl pointer-events-none"></div>

        <form id="search-form" onsubmit="handleSearch(event)" class="flex flex-col gap-4">
          <div class="flex flex-col sm:flex-row gap-3">
            <div class="relative flex-1">
              <i class="fa-solid fa-search absolute left-4 top-1/2 -translate-y-1/2 text-slate-500"></i>
              <input
                id="search-query"
                type="text"
                placeholder="Enter scientific query (e.g. polybenzoxazole zylon ionogel conductivity)"
                required
                class="w-full bg-slate-950 border border-slate-800 focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 rounded-xl pl-11 pr-4 py-3 text-slate-100 placeholder-slate-500 text-sm outline-none transition"
              />
            </div>
            <button
              id="search-btn"
              type="submit"
              class="bg-emerald-500 hover:bg-emerald-600 active:scale-[0.98] text-slate-950 font-bold px-6 py-3 rounded-xl transition flex items-center justify-center gap-2 text-sm shadow-lg shadow-emerald-500/20"
            >
              <span>Search 12 Engines</span>
              <i class="fa-solid fa-bolt"></i>
            </button>
          </div>

          <!-- Filters -->
          <div class="flex flex-wrap items-center justify-between gap-4 pt-2 border-t border-slate-800/60 text-xs text-slate-400">
            <div class="flex items-center gap-3">
              <span class="font-medium text-slate-300">Engines:</span>
              <span class="bg-slate-800 px-2.5 py-1 rounded-md text-emerald-400 font-mono">OpenAlex • Crossref • arXiv • S2 • Scopus • Europe PMC • CORE • PubMed • DOAJ • DataCite • OSTI • Zenodo</span>
            </div>
            <div class="flex items-center gap-2">
              <label for="top-n-select" class="font-medium text-slate-300">Top Enriched:</label>
              <select id="top-n-select" class="bg-slate-950 border border-slate-800 rounded px-2 py-1 text-slate-200 outline-none">
                <option value="6">6 papers</option>
                <option value="10" selected>10 papers</option>
                <option value="15">15 papers</option>
              </select>
            </div>
          </div>
        </form>
      </div>

      <!-- Loading State -->
      <div id="search-loading" class="hidden py-16 flex flex-col items-center justify-center gap-4 text-center">
        <div class="w-12 h-12 border-4 border-emerald-500/20 border-t-emerald-500 rounded-full animate-spin"></div>
        <div>
          <p class="font-semibold text-slate-200 text-base">Querying 12 Scientific Literature Engines concurrently...</p>
          <p class="text-xs text-slate-500 mt-1">Deduplicating DOIs, resolving Unpaywall OA PDFs, and checking scite.ai Smart Citations</p>
        </div>
      </div>

      <!-- Search Results Container -->
      <div id="search-results-container" class="hidden flex flex-col gap-6">
        <!-- Results Summary Bar -->
        <div class="flex flex-wrap items-center justify-between gap-4 bg-slate-900/60 border border-slate-800/80 px-5 py-3.5 rounded-xl">
          <div class="flex items-center gap-4 text-xs sm:text-sm">
            <span class="text-slate-400">Retrieved: <b id="stat-total" class="text-emerald-400 font-bold">0</b></span>
            <span class="text-slate-600">|</span>
            <span class="text-slate-400">Synthesis Top: <b id="stat-shown" class="text-slate-200 font-bold">0</b></span>
          </div>

          <!-- Export Actions -->
          <div class="flex items-center gap-2">
            <button onclick="exportReferences('bibtex')" class="bg-slate-800 hover:bg-slate-700 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-700 flex items-center gap-1.5 transition">
              <i class="fa-solid fa-file-export text-emerald-400"></i> Export BibTeX (.bib)
            </button>
            <button onclick="exportReferences('ris')" class="bg-slate-800 hover:bg-slate-700 text-xs font-semibold px-3 py-1.5 rounded-lg border border-slate-700 flex items-center gap-1.5 transition">
              <i class="fa-solid fa-quote-right text-teal-400"></i> Export RIS (.ris)
            </button>
          </div>
        </div>

        <!-- Comparative Synthesis Matrix (SciSpace / Elicit Style) -->
        <div class="bg-slate-900 border border-slate-800 rounded-2xl p-5 overflow-hidden flex flex-col gap-3">
          <div class="flex items-center justify-between">
            <h3 class="font-bold text-sm text-slate-200 flex items-center gap-2">
              <i class="fa-solid fa-table-cells text-emerald-400"></i> Comparative Synthesis Matrix (SciSpace & Elicit Style)
            </h3>
            <span class="text-[11px] text-slate-500">Automated experimental extraction</span>
          </div>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs text-slate-300 border-collapse">
              <thead>
                <tr class="border-b border-slate-800 bg-slate-950/60 text-slate-400 font-semibold">
                  <th class="py-3 px-3">Paper / Year</th>
                  <th class="py-3 px-3">Polymer Matrix</th>
                  <th class="py-3 px-3">Ionic Liquid</th>
                  <th class="py-3 px-3">Conductivity (σ)</th>
                  <th class="py-3 px-3">Thermal (Td)</th>
                  <th class="py-3 px-3">Modulus</th>
                  <th class="py-3 px-3 text-center">scite.ai Consensus</th>
                  <th class="py-3 px-3 text-center">Full-Text</th>
                </tr>
              </thead>
              <tbody id="matrix-tbody" class="divide-y divide-slate-800/60">
                <!-- Rows inserted dynamically -->
              </tbody>
            </table>
          </div>
        </div>

        <!-- Discovered Articles Cards -->
        <div class="flex flex-col gap-4">
          <h3 class="font-bold text-sm text-slate-200 flex items-center gap-2">
            <i class="fa-solid fa-book-open text-emerald-400"></i> Ranked Literature Articles & Empirical Consensus
          </h3>
          <div id="articles-list" class="flex flex-col gap-4">
            <!-- Article Cards inserted dynamically -->
          </div>
        </div>
      </div>
    </section>

    <!-- TAB 2: CITATION GRAPH SNOWBALLING -->
    <section id="tab-graph" class="hidden flex flex-col gap-6">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <form onsubmit="handleGraph(event)" class="flex flex-col gap-4">
          <h3 class="font-bold text-base text-slate-200 flex items-center gap-2">
            <i class="fa-solid fa-diagram-project text-emerald-400"></i> Connected Papers & Citation Snowballing
          </h3>
          <p class="text-xs text-slate-400">
            Enter a seed DOI or paper title to explore bibliographically coupled papers (Connected Papers style), forward citing works, or foundational backward references.
          </p>
          <div class="flex flex-col sm:flex-row gap-3">
            <input
              id="graph-seed"
              type="text"
              placeholder="e.g. 10.1039/c9ta01153a or Ionogels: High-Performance Solid Electrolytes"
              required
              class="flex-1 bg-slate-950 border border-slate-800 focus:border-emerald-500 rounded-xl px-4 py-3 text-slate-100 placeholder-slate-500 text-sm outline-none"
            />
            <select id="graph-mode" class="bg-slate-950 border border-slate-800 rounded-xl px-4 py-3 text-slate-200 text-sm outline-none">
              <option value="related" selected>Co-Citations (Connected Papers)</option>
              <option value="forward">Forward Citing (Who cites this?)</option>
              <option value="backward">Backward References (Foundational)</option>
            </select>
            <button
              type="submit"
              class="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-6 py-3 rounded-xl text-sm transition"
            >
              Explore Graph
            </button>
          </div>
        </form>
      </div>

      <div id="graph-loading" class="hidden py-12 flex flex-col items-center justify-center gap-3">
        <div class="w-10 h-10 border-4 border-emerald-500/20 border-t-emerald-500 rounded-full animate-spin"></div>
        <p class="text-sm text-slate-400">Building citation graph from OpenAlex and scite.ai...</p>
      </div>

      <div id="graph-results" class="hidden flex flex-col gap-4">
        <!-- Seed banner -->
        <div id="graph-seed-banner" class="bg-slate-900 border border-emerald-500/30 rounded-xl p-4"></div>
        <!-- Connected works -->
        <div id="graph-works-list" class="flex flex-col gap-4"></div>
      </div>
    </section>

    <!-- TAB 3: PYMUPDF DEEP READER -->
    <section id="tab-reader" class="hidden flex flex-col gap-6">
      <div class="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl">
        <form onsubmit="handleDeepRead(event)" class="flex flex-col gap-4">
          <h3 class="font-bold text-base text-slate-200 flex items-center gap-2">
            <i class="fa-solid fa-file-pdf text-emerald-400"></i> PyMuPDF In-Memory Deep Full-Text Reader
          </h3>
          <p class="text-xs text-slate-400">
            Stream an open-access PDF directly into memory (zero disk footprint) to parse full methodology, material recipes, and experimental results.
          </p>
          <div class="flex flex-col sm:flex-row gap-3">
            <input
              id="reader-target"
              type="text"
              placeholder="Enter DOI (e.g. 10.1038/s41563-020-00831-2) or direct PDF URL"
              required
              class="flex-1 bg-slate-950 border border-slate-800 focus:border-emerald-500 rounded-xl px-4 py-3 text-slate-100 placeholder-slate-500 text-sm outline-none"
            />
            <button
              type="submit"
              class="bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold px-6 py-3 rounded-xl text-sm transition"
            >
              Stream & Extract
            </button>
          </div>
        </form>
      </div>

      <div id="reader-loading" class="hidden py-12 flex flex-col items-center justify-center gap-3">
        <div class="w-10 h-10 border-4 border-emerald-500/20 border-t-emerald-500 rounded-full animate-spin"></div>
        <p class="text-sm text-slate-400">Downloading PDF into memory and extracting experimental parameters...</p>
      </div>

      <div id="reader-results" class="hidden flex flex-col gap-6">
        <!-- Metrics -->
        <div id="reader-metrics" class="grid grid-cols-2 sm:grid-cols-4 gap-4"></div>
        <!-- Extracted Properties -->
        <div id="reader-props" class="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col gap-3"></div>
        <!-- Sections -->
        <div id="reader-sections" class="flex flex-col gap-4"></div>
      </div>
    </section>

  </main>

  <footer class="border-t border-slate-800/80 bg-slate-950 py-6 text-center text-xs text-slate-500">
    <p>LitDiscovery © 2026 Rehan & Lab Contributors (University of Arizona) — MIT License</p>
  </footer>

  <script>
    let currentSearchResults = [];

    function switchTab(tab) {
      ['search', 'graph', 'reader'].forEach(t => {
        document.getElementById(`tab-${t}`).classList.add('hidden');
        document.getElementById(`tab-${t}-btn`).classList.replace('text-emerald-400', 'text-slate-400');
        document.getElementById(`tab-${t}-btn`).classList.replace('border-emerald-500', 'border-transparent');
      });
      document.getElementById(`tab-${tab}`).classList.remove('hidden');
      document.getElementById(`tab-${tab}-btn`).classList.replace('text-slate-400', 'text-emerald-400');
      document.getElementById(`tab-${tab}-btn`).classList.replace('border-transparent', 'border-emerald-500');
    }

    async function handleSearch(e) {
      e.preventDefault();
      const query = document.getElementById('search-query').value.trim();
      const topN = parseInt(document.getElementById('top-n-select').value);
      if (!query) return;

      document.getElementById('search-loading').classList.remove('hidden');
      document.getElementById('search-results-container').classList.add('hidden');

      try {
        const resp = await fetch('/api/search', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ query: query, top_n: topN })
        });
        const data = await resp.json();
        currentSearchResults = data.articles || [];
        renderSearchResults(data);
      } catch (err) {
        alert('Search error: ' + err.message);
      } finally {
        document.getElementById('search-loading').classList.add('hidden');
      }
    }

    function renderSearchResults(data) {
      document.getElementById('stat-total').textContent = data.total_articles_retrieved || 0;
      document.getElementById('stat-shown').textContent = data.total_articles_shown || 0;

      // Matrix
      const tbody = document.getElementById('matrix-tbody');
      tbody.innerHTML = '';
      (data.synthesis_matrix || []).forEach(r => {
        const sc = r.smart_citations || {};
        let scBadge = '<span class="text-slate-500 text-[11px]">—</span>';
        if (sc.total_citations > 0) {
          scBadge = `<span class="inline-flex items-center gap-1 font-semibold text-[11px]">
            <span class="text-emerald-400">🟢 ${sc.supporting || 0}</span> /
            <span class="text-rose-400">🔴 ${sc.contrasting || 0}</span>
          </span>`;
        }
        const pdfLink = r.open_access_pdf
          ? `<a href="${r.open_access_pdf}" target="_blank" class="text-emerald-400 hover:underline"><i class="fa-solid fa-file-pdf mr-1"></i>PDF</a>`
          : '<span class="text-slate-600">—</span>';

        const row = document.createElement('tr');
        row.className = 'hover:bg-slate-800/40 transition';
        row.innerHTML = `
          <td class="py-2.5 px-3 font-medium text-slate-200">${escapeHtml(r.paper)}</td>
          <td class="py-2.5 px-3 font-mono text-emerald-300">${(r.polymer_matrix || []).join(', ') || '—'}</td>
          <td class="py-2.5 px-3 font-mono text-cyan-300">${(r.ionic_liquid || []).join(', ') || '—'}</td>
          <td class="py-2.5 px-3 text-amber-300">${(r.ionic_conductivity || []).join(', ') || '—'}</td>
          <td class="py-2.5 px-3">${(r.thermal_stability || []).join(', ') || '—'}</td>
          <td class="py-2.5 px-3">${(r.mechanical_properties || []).join(', ') || '—'}</td>
          <td class="py-2.5 px-3 text-center">${scBadge}</td>
          <td class="py-2.5 px-3 text-center">${pdfLink}</td>
        `;
        tbody.appendChild(row);
      });

      // Article Cards
      const list = document.getElementById('articles-list');
      list.innerHTML = '';
      (data.articles || []).forEach((art, idx) => {
        const sc = art.smart_citations || {};
        const card = document.createElement('div');
        card.className = 'bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col gap-3 hover:border-slate-700 transition shadow';

        let scitePill = '';
        if (sc.total_citations > 0) {
          scitePill = `
            <div class="inline-flex items-center gap-2 px-3 py-1 rounded-lg bg-slate-950 border border-slate-800 text-xs">
              <span class="font-bold text-slate-400">scite.ai:</span>
              <span class="text-emerald-400 font-semibold"><i class="fa-solid fa-circle-check mr-1"></i>${sc.supporting || 0} supporting</span>
              <span class="text-slate-600">•</span>
              <span class="text-rose-400 font-semibold"><i class="fa-solid fa-circle-xmark mr-1"></i>${sc.contrasting || 0} contrasting</span>
              <span class="text-slate-600">•</span>
              <span class="text-slate-400">${sc.total_citations} total citations</span>
            </div>
          `;
        }

        const authorsStr = (art.authors || []).join(', ') || 'Unknown Authors';
        const yearStr = art.year ? `(${art.year})` : '';
        const journalStr = art.journal || art.source_database || 'Scientific Journal';
        const score = art.relevance ? `${art.relevance.score_percent}% match` : '';

        card.innerHTML = `
          <div class="flex items-start justify-between gap-4">
            <div>
              <h4 class="font-bold text-slate-100 text-base leading-snug hover:text-emerald-400 transition cursor-pointer" onclick="openDeepReader('${art.doi || ''}')">
                ${escapeHtml(art.title)}
              </h4>
              <p class="text-xs text-slate-400 mt-1">
                <span class="text-slate-300 font-medium">${escapeHtml(authorsStr)}</span> ${yearStr} &middot; <span class="italic text-slate-400">${escapeHtml(journalStr)}</span>
              </p>
            </div>
            ${score ? `<span class="px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 whitespace-nowrap">${score}</span>` : ''}
          </div>

          <p class="text-xs text-slate-300 line-clamp-3 leading-relaxed bg-slate-950/40 p-3 rounded-xl border border-slate-800/60">
            ${escapeHtml(art.abstract || 'No abstract preview available.')}
          </p>

          <div class="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-slate-800/80">
            <div class="flex items-center gap-2">
              ${scitePill}
            </div>
            <div class="flex items-center gap-2 text-xs">
              ${art.doi ? `<a href="${art.doi}" target="_blank" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-1.5 transition"><i class="fa-solid fa-arrow-up-right-from-square text-[10px]"></i> DOI</a>` : ''}
              ${art.open_access_pdf ? `<a href="${art.open_access_pdf}" target="_blank" class="px-3 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/30 flex items-center gap-1.5 transition"><i class="fa-solid fa-file-pdf"></i> Read PDF</a>` : ''}
              ${art.doi ? `<button onclick="launchGraph('${art.doi}')" class="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-1.5 transition"><i class="fa-solid fa-diagram-project text-emerald-400"></i> Explore Graph</button>` : ''}
            </div>
          </div>
        `;
        list.appendChild(card);
      });

      document.getElementById('search-results-container').classList.remove('hidden');
    }

    async function exportReferences(format) {
      if (!currentSearchResults.length) {
        alert('Please run a search first to export references.');
        return;
      }
      try {
        const resp = await fetch('/api/export', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ format: format, articles: currentSearchResults })
        });
        const blob = await resp.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = format === 'bibtex' ? 'references.bib' : 'references.ris';
        document.body.appendChild(a);
        a.click();
        a.remove();
      } catch (err) {
        alert('Export error: ' + err.message);
      }
    }

    function launchGraph(doi) {
      switchTab('graph');
      document.getElementById('graph-seed').value = doi;
      document.getElementById('graph-mode').value = 'related';
      handleGraph(new Event('submit'));
    }

    function openDeepReader(doi) {
      if (!doi) return;
      switchTab('reader');
      document.getElementById('reader-target').value = doi;
      handleDeepRead(new Event('submit'));
    }

    async function handleGraph(e) {
      if (e) e.preventDefault();
      const seed = document.getElementById('graph-seed').value.trim();
      const mode = document.getElementById('graph-mode').value;
      if (!seed) return;

      document.getElementById('graph-loading').classList.remove('hidden');
      document.getElementById('graph-results').classList.add('hidden');

      try {
        const resp = await fetch('/api/graph', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ seed: seed, mode: mode })
        });
        const data = await resp.json();
        renderGraphResults(data);
      } catch (err) {
        alert('Graph error: ' + err.message);
      } finally {
        document.getElementById('graph-loading').classList.add('hidden');
      }
    }

    function renderGraphResults(data) {
      if (data.status !== 'success') {
        alert('Could not resolve graph: ' + (data.error || data.message || 'Unknown error'));
        return;
      }
      const seed = data.seed_paper || data.seed_work || {};
      const banner = document.getElementById('graph-seed-banner');
      banner.innerHTML = `
        <span class="text-[11px] font-bold uppercase tracking-wider text-emerald-400">Seed Paper</span>
        <h4 class="font-bold text-slate-100 text-sm mt-1">${escapeHtml(seed.title || 'Seed Work')}</h4>
        <div class="flex items-center gap-3 text-xs text-slate-400 mt-1">
          <span>${seed.year ? seed.year : ''}</span>
          ${seed.doi ? `<a href="${seed.doi}" target="_blank" class="text-emerald-400 hover:underline">${seed.doi}</a>` : ''}
          <span class="px-2 py-0.5 rounded bg-slate-800 text-slate-300 font-mono text-[10px] uppercase">${data.mode || data.graph_mode}</span>
        </div>
      `;

      const list = document.getElementById('graph-works-list');
      list.innerHTML = '';
      (data.connected_works || []).forEach(w => {
        const card = document.createElement('div');
        card.className = 'bg-slate-900 border border-slate-800 rounded-xl p-4 flex flex-col gap-2.5';
        const sc = w.smart_citations || {};
        let scBadge = '';
        if (sc.total_citations > 0) {
          scBadge = `<span class="text-xs text-slate-400">scite.ai: <b class="text-emerald-400">${sc.supporting || 0} Supp</b> / <b class="text-rose-400">${sc.contrasting || 0} Cont</b></span>`;
        }
        card.innerHTML = `
          <div class="flex items-start justify-between gap-3">
            <h5 class="font-semibold text-slate-200 text-sm leading-snug">${escapeHtml(w.title)}</h5>
            <span class="text-xs text-slate-400">${w.year || ''}</span>
          </div>
          <p class="text-xs text-slate-400">${(w.authors || []).join(', ') || 'Unknown Authors'}</p>
          <div class="flex items-center justify-between text-xs pt-2 border-t border-slate-800">
            <div>${scBadge}</div>
            <div class="flex items-center gap-2">
              ${w.doi ? `<a href="${w.doi}" target="_blank" class="text-slate-300 hover:text-white"><i class="fa-solid fa-arrow-up-right-from-square"></i> DOI</a>` : ''}
              ${w.open_access_pdf ? `<a href="${w.open_access_pdf}" target="_blank" class="text-emerald-400 hover:underline"><i class="fa-solid fa-file-pdf"></i> PDF</a>` : ''}
            </div>
          </div>
        `;
        list.appendChild(card);
      });

      document.getElementById('graph-results').classList.remove('hidden');
    }

    async function handleDeepRead(e) {
      if (e) e.preventDefault();
      const target = document.getElementById('reader-target').value.trim();
      if (!target) return;

      document.getElementById('reader-loading').classList.remove('hidden');
      document.getElementById('reader-results').classList.add('hidden');

      try {
        const resp = await fetch('/api/read', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ target: target })
        });
        const data = await resp.json();
        renderDeepRead(data);
      } catch (err) {
        alert('Deep read error: ' + err.message);
      } finally {
        document.getElementById('reader-loading').classList.add('hidden');
      }
    }

    function renderDeepRead(data) {
      if (data.status !== 'success') {
        alert('Deep read failed: ' + (data.error || data.message || 'Unknown error'));
        return;
      }

      // Metrics
      const mContainer = document.getElementById('reader-metrics');
      mContainer.innerHTML = `
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span class="text-xs text-slate-500">Pages Analyzed</span>
          <p class="text-xl font-black text-emerald-400 mt-1">${data.pages_analyzed} / ${data.total_pages}</p>
        </div>
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4">
          <span class="text-xs text-slate-500">Characters Streamed</span>
          <p class="text-xl font-black text-slate-200 mt-1">${(data.character_count || 0).toLocaleString()}</p>
        </div>
        <div class="bg-slate-900 border border-slate-800 rounded-xl p-4 col-span-2">
          <span class="text-xs text-slate-500">Resolved Source PDF</span>
          <p class="text-xs text-emerald-400 truncate mt-1"><a href="${data.pdf_url}" target="_blank">${data.pdf_url}</a></p>
        </div>
      `;

      // Extracted Properties
      const pContainer = document.getElementById('reader-props');
      const p = data.extracted_properties || {};
      pContainer.innerHTML = `
        <h4 class="font-bold text-sm text-slate-200 flex items-center gap-2">
          <i class="fa-solid fa-flask-vial text-emerald-400"></i> Extracted Experimental Parameters & Recipes
        </h4>
        <div class="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs mt-1">
          <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
            <span class="text-slate-500 block mb-1">Polymer Matrix:</span>
            <span class="font-mono text-emerald-300 font-semibold">${(p.polymer_matrix || []).join(', ') || 'None detected'}</span>
          </div>
          <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
            <span class="text-slate-500 block mb-1">Ionic Liquids / Salts:</span>
            <span class="font-mono text-cyan-300 font-semibold">${(p.ionic_liquids || []).join(', ') || 'None detected'}</span>
          </div>
          <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
            <span class="text-slate-500 block mb-1">Ionic Conductivity:</span>
            <span class="font-mono text-amber-300 font-semibold">${(p.ionic_conductivity || []).join(', ') || 'None detected'}</span>
          </div>
          <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
            <span class="text-slate-500 block mb-1">Thermal Stability:</span>
            <span class="font-mono text-rose-300 font-semibold">${(p.thermal_properties || []).join(', ') || 'None detected'}</span>
          </div>
          <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
            <span class="text-slate-500 block mb-1">Mechanical Modulus:</span>
            <span class="font-mono text-indigo-300 font-semibold">${(p.mechanical_modulus || []).join(', ') || 'None detected'}</span>
          </div>
          <div class="bg-slate-950 p-3 rounded-lg border border-slate-800">
            <span class="text-slate-500 block mb-1">Stretchability / Elongation:</span>
            <span class="font-mono text-teal-300 font-semibold">${(p.stretchability || []).join(', ') || 'None detected'}</span>
          </div>
        </div>
      `;

      // Sections
      const sContainer = document.getElementById('reader-sections');
      const s = data.sections || {};
      sContainer.innerHTML = '';
      [
        { title: 'Materials and Experimental Methods', content: s.experimental_methods },
        { title: 'Results & Characterization Discussion', content: s.results_and_discussion },
        { title: 'Conclusions & Key Takeaways', content: s.conclusions }
      ].forEach(sec => {
        if (sec.content) {
          const block = document.createElement('div');
          block.className = 'bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col gap-2';
          block.innerHTML = `
            <h5 class="font-bold text-sm text-slate-200">${sec.title}</h5>
            <div class="text-xs text-slate-300 leading-relaxed max-h-64 overflow-y-auto bg-slate-950 p-4 rounded-xl border border-slate-800/80 whitespace-pre-wrap font-sans">
              ${escapeHtml(sec.content)}
            </div>
          `;
          sContainer.appendChild(block);
        }
      });

      document.getElementById('reader-results').classList.remove('hidden');
    }

    function escapeHtml(text) {
      if (!text) return '';
      return String(text)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
    }
  </script>
</body>
</html>
"""


class SearchRequest(BaseModel):
    query: str
    engines: Optional[List[str]] = None
    limit: Optional[int] = 5
    top_n: Optional[int] = 10


class GraphRequest(BaseModel):
    seed: str
    mode: Optional[str] = "related"
    limit: Optional[int] = 6


class DeepReadRequest(BaseModel):
    target: str
    max_pages: Optional[int] = 30


class ExportRequest(BaseModel):
    format: str = "bibtex"
    articles: List[Dict[str, Any]]


@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=HTML_TEMPLATE, status_code=200)


@app.get("/health")
def health():
    return {
        "status": "healthy",
        "engines_available": len(AVAILABLE_ENGINES),
        "engines": list(AVAILABLE_ENGINES.keys())
    }


@app.post("/api/search")
def api_search(req: SearchRequest):
    return search_literature(
        query_text=req.query,
        selected_engines=req.engines,
        limit_per_engine=req.limit or 5,
        top_n=req.top_n or 10,
        enrich=True
    )


@app.post("/api/graph")
def api_graph(req: GraphRequest):
    return explore_citation_graph(
        seed_doi_or_query=req.seed,
        mode=req.mode or "related",
        limit=req.limit or 6
    )


@app.post("/api/read")
def api_read(req: DeepReadRequest):
    return deep_read_pdf(
        target_doi_or_url=req.target,
        max_pages=req.max_pages or 30
    )


@app.post("/api/export")
def api_export(req: ExportRequest):
    with tempfile.TemporaryDirectory() as td:
        bib_path = os.path.join(td, "refs.bib") if req.format == "bibtex" else None
        ris_path = os.path.join(td, "refs.ris") if req.format != "bibtex" else None
        export_zotero_references(req.articles, bib_path=bib_path, ris_path=ris_path)

        if bib_path and os.path.exists(bib_path):
            with open(bib_path, "r", encoding="utf-8") as f:
                content = f.read()
            return Response(
                content=content,
                media_type="application/x-bibtex",
                headers={"Content-Disposition": "attachment; filename=references.bib"}
            )
        elif ris_path and os.path.exists(ris_path):
            with open(ris_path, "r", encoding="utf-8") as f:
                content = f.read()
            return Response(
                content=content,
                media_type="application/x-research-info-systems",
                headers={"Content-Disposition": "attachment; filename=references.ris"}
            )
        else:
            raise HTTPException(status_code=400, detail="Could not generate citation export.")


def run_server(host: str = "127.0.0.1", port: int = 8000):
    import uvicorn
    print(f"🚀 Starting LitDiscovery Web UI on http://{host}:{port}")
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    run_server()

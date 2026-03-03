#!/usr/bin/env node
/**
 * Cash Content → Obsidian Scraper
 * Extrae transcripts de videos Wistia en Circle.so y crea notas en Obsidian
 */

import https from 'https';
import fs from 'fs';
import path from 'path';

// ─── Config ─────────────────────────────────────────────────────────────────
const BASE_URL = 'https://cash-content.circle.so';
const OBSIDIAN_DIR = '/home/node/obsidian-vault/Marketing Inmobiliario/Cash Content';
const DELAY_MS = 2500; // pausa entre requests para no bannearse

const COOKIE = `ahoy_visitor=1c6a789f-b367-499a-af7e-0e0f524b3a51; cookies_enabled=true; user_session_identifier=AUwdZ1iHFhXupfOoKYybxmoC2zncgWFIjWdrYL563LxbQVB9clm8dmEEvkJc8IAXxJZuRgbOrgfpVK9F6aGtcc%2Fi%2FUFRBKBtX8Y4BEtRK%2BjBuIE8XnLzGjTPpTHltAQFeqtJ8AL0U3buSp42F387W5PdzgOcG4C08mll2tOjeX%2B0bV31cNt92aohC9%2FiMg1v1kt%2Fcoyakou%2Bp1d%2BNj7PNBQXYp%2FY52rc7zx9e157N%2BVB8jLoZyhnKg2YlpcrpxONAQF9dPVS%2FZ7hxjw%2Fng%3D%3D--RPZpaj%2BAaKVREGBx--x%2B2DkCDtow4EkrfxJRHbFA%3D%3D; browser_time_zone=America/Chicago; __stripe_mid=ef68688f-787b-4b8e-86cb-8869a2d7ce88a51edc; ahoy_visit=1fe45159-f2e7-41cc-8df1-166a2e557237`;

// ─── All 42 Lessons ──────────────────────────────────────────────────────────
const LESSONS = [
  // Punto de partida
  { section: 'Punto de partida', title: 'Bienvenida e introducción', url: '/c/module-1/sections/398162/lessons/1482797' },
  { section: 'Punto de partida', title: 'Preparación para este camino', url: '/c/module-1/sections/398162/lessons/1483389' },
  { section: 'Punto de partida', title: 'Encuentra tu propósito', url: '/c/module-1/sections/398162/lessons/1482798' },
  { section: 'Punto de partida', title: 'Inteligencia emocional para creadores', url: '/c/module-1/sections/398162/lessons/1483386' },
  { section: 'Punto de partida', title: '¿Cómo duplicar un archivo de Notion?', url: '/c/module-1/sections/398162/lessons/1502752' },
  // Bases sólidas para crecer
  { section: 'Bases sólidas para crecer', title: 'Define tu seguidor ideal (perfil comprador)', url: '/c/module-1/sections/385287/lessons/1474643' },
  { section: 'Bases sólidas para crecer', title: 'Optimiza tu biografía para atraer a la gente correcta', url: '/c/module-1/sections/385287/lessons/1433939' },
  { section: 'Bases sólidas para crecer', title: 'Investiga referentes estratégicos', url: '/c/module-1/sections/385287/lessons/1447519' },
  { section: 'Bases sólidas para crecer', title: '[TUTORIAL] Investigación de Referentes', url: '/c/module-1/sections/385287/lessons/1433958' },
  { section: 'Bases sólidas para crecer', title: 'Crea tu árbol de contenido (temas principales)', url: '/c/module-1/sections/385287/lessons/1433988' },
  { section: 'Bases sólidas para crecer', title: 'Quiz – Bases sólidas', url: '/c/module-1/sections/385287/lessons/1502966' },
  { section: 'Bases sólidas para crecer', title: 'Pasos a Seguir', url: '/c/module-1/sections/385287/lessons/1576701' },
  // Ideas que nunca se acaban
  { section: 'Ideas que nunca se acaban', title: 'Introducción a la generación de ideas', url: '/c/module-1/sections/385296/lessons/1495317' },
  { section: 'Ideas que nunca se acaban', title: 'Cómo encontrar ideas de contenido ilimitadas', url: '/c/module-1/sections/385296/lessons/1447529' },
  { section: 'Ideas que nunca se acaban', title: '[Tutorial] Tiktok & Instagram Sorter', url: '/c/module-1/sections/385296/lessons/1433964' },
  { section: 'Ideas que nunca se acaban', title: '[Tutorial] Viralfindr', url: '/c/module-1/sections/385296/lessons/1433966' },
  { section: 'Ideas que nunca se acaban', title: '"Roba como un artista" (adaptar sin copiar)', url: '/c/module-1/sections/385296/lessons/1486330' },
  { section: 'Ideas que nunca se acaban', title: 'Pasos a Seguir', url: '/c/module-1/sections/385296/lessons/1576707' },
  // De Viewer a Cliente
  { section: 'De Viewer a Cliente', title: 'Introducción al sistema CCV', url: '/c/module-1/sections/385299/lessons/1509095' },
  { section: 'De Viewer a Cliente', title: 'Contenido de Crecimiento', url: '/c/module-1/sections/385299/lessons/1433989' },
  { section: 'De Viewer a Cliente', title: 'Contenido de Conexión', url: '/c/module-1/sections/385299/lessons/1433991' },
  { section: 'De Viewer a Cliente', title: 'Contenido de Venta', url: '/c/module-1/sections/385299/lessons/1433992' },
  { section: 'De Viewer a Cliente', title: 'Cómo estructurar tu estrategia de contenido', url: '/c/module-1/sections/385299/lessons/1433994' },
  { section: 'De Viewer a Cliente', title: 'Pasos a Seguir', url: '/c/module-1/sections/385299/lessons/1576708' },
  { section: 'De Viewer a Cliente', title: 'Quiz - De Viewer a Cliente', url: '/c/module-1/sections/385299/lessons/1503039' },
  // Sistema de Creación de Contenido
  { section: 'Sistema de Creación de Contenido', title: 'Plantilla de producción de contenido (Notion)', url: '/c/module-1/sections/385300/lessons/1433996' },
  // Cash Content GPT
  { section: 'Cash Content GPT', title: 'Cómo usar Cash Content GPT para generar ganchos y guiones', url: '/c/module-1/sections/417665/lessons/2207932' },
  // Copywriting
  { section: 'Copywriting', title: 'Componentes de un guión claro', url: '/c/module-1/sections/385301/lessons/1482799' },
  { section: 'Copywriting', title: 'Recursos de Copywriting', url: '/c/module-1/sections/385301/lessons/1482802' },
  { section: 'Copywriting', title: 'Plantillas para Videos', url: '/c/module-1/sections/385301/lessons/1482804' },
  { section: 'Copywriting', title: 'Pasos a Seguir', url: '/c/module-1/sections/385301/lessons/1576709' },
  // Grabación y Edición
  { section: 'Grabación y Edición', title: 'Cómo organizar tu set up para grabar', url: '/c/module-1/sections/385367/lessons/1434344' },
  { section: 'Grabación y Edición', title: 'Cómo preparar tu guión para grabar', url: '/c/module-1/sections/385367/lessons/1434345' },
  { section: 'Grabación y Edición', title: 'Cómo grabar paso a paso', url: '/c/module-1/sections/385367/lessons/1495351' },
  { section: 'Grabación y Edición', title: 'Edición en Capcut', url: '/c/module-1/sections/385367/lessons/1434346' },
  { section: 'Grabación y Edición', title: 'Ideas de B-rolls para enriquecer tu contenido', url: '/c/module-1/sections/385367/lessons/1495332' },
  { section: 'Grabación y Edición', title: 'Pasos a Seguir', url: '/c/module-1/sections/385367/lessons/1576853' },
  // Llamadas Grupales
  { section: 'Llamadas Grupales', title: 'Preguntas y respuestas - Reto de meditación - Marzo 27', url: '/c/module-1/sections/634851/lessons/2406950' },
  { section: 'Llamadas Grupales', title: 'Llamada Junio 23', url: '/c/module-1/sections/634851/lessons/2402508' },
  { section: 'Llamadas Grupales', title: 'Llamada Q&A Junio 30', url: '/c/module-1/sections/634851/lessons/2439456' },
  { section: 'Llamadas Grupales', title: 'Llamada Q&A Julio 7', url: '/c/module-1/sections/634851/lessons/2460694' },
  { section: 'Llamadas Grupales', title: 'Llamada Q&A Julio 18', url: '/c/module-1/sections/634851/lessons/2518476' },
];

// ─── Helpers ─────────────────────────────────────────────────────────────────
function fetchUrl(url, headers = {}) {
  return new Promise((resolve, reject) => {
    const req = https.get(url, { headers }, (res) => {
      // Handle redirects
      if (res.statusCode >= 300 && res.statusCode < 400 && res.headers.location) {
        return fetchUrl(res.headers.location, headers).then(resolve).catch(reject);
      }
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve({ status: res.statusCode, body: data }));
    });
    req.on('error', reject);
    req.setTimeout(15000, () => { req.destroy(); reject(new Error('timeout')); });
  });
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function extractWistiaId(html) {
  // Match wistia iframe src or data-video-id or wistia script embed
  const patterns = [
    /fast\.wistia\.(?:net|com)\/embed\/iframe\/([a-zA-Z0-9]+)/,
    /wistia_embed.*?id=([a-zA-Z0-9]+)/,
    /fast\.wistia\.net\/embed\/medias\/([a-zA-Z0-9]+)/,
    /"wistia_video_id"\s*:\s*"([a-zA-Z0-9]+)"/,
    /wistia\.com\/medias\/([a-zA-Z0-9]+)/,
  ];
  for (const pattern of patterns) {
    const match = html.match(pattern);
    if (match) return match[1];
  }
  return null;
}

function parseVTT(vttContent) {
  const lines = vttContent.split('\n');
  const textLines = [];
  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    if (trimmed.startsWith('WEBVTT')) continue;
    if (trimmed.includes('-->')) continue;
    if (/^\d+$/.test(trimmed)) continue; // cue numbers
    textLines.push(trimmed);
  }
  // Join and clean up duplicate spaces
  return textLines.join(' ').replace(/\s+/g, ' ').trim();
}

function extractPageText(html) {
  // Extract any visible text content from the lesson page (for non-video lessons)
  // Look for the main lesson content area
  const contentMatch = html.match(/class="lesson-content[^"]*"[^>]*>([\s\S]*?)<\/div>/);
  if (contentMatch) {
    return contentMatch[1].replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
  }
  return null;
}

function sanitizeFilename(str) {
  return str
    .replace(/[/\\?%*:|"<>]/g, '-')
    .replace(/\s+/g, ' ')
    .trim();
}

function toSlug(str) {
  return str
    .toLowerCase()
    .replace(/[áàâä]/g, 'a').replace(/[éèêë]/g, 'e')
    .replace(/[íìîï]/g, 'i').replace(/[óòôö]/g, 'o')
    .replace(/[úùûü]/g, 'u').replace(/[ñ]/g, 'n')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '');
}

function createObsidianNote(lesson, lessonNumber, transcript, rawContent) {
  const date = new Date().toISOString().split('T')[0];
  const fullUrl = `${BASE_URL}${lesson.url}`;
  const hasTranscript = transcript && transcript.length > 50;

  let note = `---
title: "${lesson.title.replace(/"/g, "'")}"
section: "${lesson.section}"
lesson_number: ${lessonNumber}
source_url: "${fullUrl}"
course: "Cash Content - Maria Duran"
tags:
  - marketing-inmobiliario
  - cash-content
  - ${toSlug(lesson.section)}
created: ${date}
---

# ${lesson.title}

> **Sección:** ${lesson.section}  
> **Lección:** ${lessonNumber} de 42  
> **Fuente:** [Ver en Circle](${fullUrl})

`;

  if (hasTranscript) {
    note += `## Transcript

${transcript}

`;
  } else if (rawContent) {
    note += `## Contenido

${rawContent}

`;
  } else {
    note += `## Contenido

_(Sin transcript disponible para esta lección)_

`;
  }

  note += `---
*Nota generada automáticamente desde Cash Content - Maria Duran*
`;

  return note;
}

// ─── Main ────────────────────────────────────────────────────────────────────
async function main() {
  console.log('🚀 Cash Content Scraper iniciado');
  console.log(`📁 Destino Obsidian: ${OBSIDIAN_DIR}`);
  console.log(`📚 Total lecciones: ${LESSONS.length}\n`);

  // Create directories
  fs.mkdirSync(OBSIDIAN_DIR, { recursive: true });

  // Create section subdirectories
  const sections = [...new Set(LESSONS.map(l => l.section))];
  for (const section of sections) {
    fs.mkdirSync(path.join(OBSIDIAN_DIR, sanitizeFilename(section)), { recursive: true });
  }

  const headers = {
    'Cookie': COOKIE,
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
    'Accept': 'text/html,application/xhtml+xml',
    'Accept-Language': 'es-ES,es;q=0.9,en;q=0.8',
  };

  const results = { success: 0, noVideo: 0, failed: 0 };

  for (let i = 0; i < LESSONS.length; i++) {
    const lesson = LESSONS[i];
    const lessonNumber = i + 1;
    const sectionDir = sanitizeFilename(lesson.section);
    const filename = `${String(lessonNumber).padStart(2, '0')} - ${sanitizeFilename(lesson.title)}.md`;
    const filepath = path.join(OBSIDIAN_DIR, sectionDir, filename);

    // Skip if already exists
    if (fs.existsSync(filepath)) {
      console.log(`⏭️  [${lessonNumber}/42] Ya existe: ${lesson.title}`);
      results.success++;
      continue;
    }

    console.log(`📖 [${lessonNumber}/42] ${lesson.title}`);

    try {
      // Fetch lesson page
      const { status, body } = await fetchUrl(`${BASE_URL}${lesson.url}`, headers);

      if (status !== 200) {
        console.log(`   ⚠️  HTTP ${status} - guardando nota sin transcript`);
        const note = createObsidianNote(lesson, lessonNumber, null, null);
        fs.writeFileSync(filepath, note, 'utf8');
        results.noVideo++;
        await sleep(DELAY_MS);
        continue;
      }

      // Extract Wistia video ID
      const wistiaId = extractWistiaId(body);
      let transcript = null;

      if (wistiaId) {
        console.log(`   🎬 Wistia ID: ${wistiaId}`);

        // Fetch VTT transcript
        try {
          const vttUrl = `https://fast.wistia.net/embed/captions/${wistiaId}.vtt`;
          const { status: vttStatus, body: vttBody } = await fetchUrl(vttUrl);

          if (vttStatus === 200 && vttBody.startsWith('WEBVTT')) {
            transcript = parseVTT(vttBody);
            console.log(`   ✅ Transcript: ${transcript.length} caracteres`);
          } else {
            console.log(`   ⚠️  Sin VTT (status ${vttStatus})`);
          }
        } catch (e) {
          console.log(`   ⚠️  Error fetching VTT: ${e.message}`);
        }
      } else {
        console.log(`   📝 Sin video (texto/quiz/recursos)`);
      }

      // Create Obsidian note
      const note = createObsidianNote(lesson, lessonNumber, transcript, null);
      fs.writeFileSync(filepath, note, 'utf8');
      console.log(`   💾 Guardado: ${filename}`);

      if (wistiaId && transcript) results.success++;
      else results.noVideo++;

    } catch (e) {
      console.log(`   ❌ Error: ${e.message}`);
      results.failed++;
      // Still create a placeholder note
      try {
        const note = createObsidianNote(lesson, lessonNumber, null, null);
        fs.writeFileSync(filepath, note, 'utf8');
      } catch {}
    }

    // Polite delay between requests
    if (i < LESSONS.length - 1) {
      await sleep(DELAY_MS);
    }
  }

  // Create index note
  const indexPath = path.join(OBSIDIAN_DIR, '00 - Índice Cash Content.md');
  let index = `---
title: "Cash Content - Índice"
course: "Cash Content - Maria Duran"
tags:
  - marketing-inmobiliario
  - cash-content
  - indice
created: ${new Date().toISOString().split('T')[0]}
---

# 📚 Cash Content - Índice Completo

> **Curso:** Cash Content por Maria Duran  
> **Plataforma:** [Circle.so](${BASE_URL})  
> **Total lecciones:** ${LESSONS.length}

`;
  let currentSection = '';
  LESSONS.forEach((lesson, i) => {
    const num = i + 1;
    if (lesson.section !== currentSection) {
      currentSection = lesson.section;
      index += `\n## ${lesson.section}\n\n`;
    }
    const sectionDir = sanitizeFilename(lesson.section);
    const filename = `${String(num).padStart(2, '0')} - ${sanitizeFilename(lesson.title)}`;
    index += `- [[${sectionDir}/${filename}|${num}. ${lesson.title}]]\n`;
  });
  fs.writeFileSync(indexPath, index, 'utf8');

  console.log(`\n✅ Completado!`);
  console.log(`   Con transcript: ${results.success}`);
  console.log(`   Sin video/quiz: ${results.noVideo}`);
  console.log(`   Errores:        ${results.failed}`);
  console.log(`\n📁 Notas en: ${OBSIDIAN_DIR}`);
}

main().catch(console.error);

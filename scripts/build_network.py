"""
build_network.py — Строит данные и HTML-визуализацию графа викилинков.

Сканирует карточки эмитентов, считает совместную встречаемость `[[викилинки]]`
и создаёт:
1. `network/graph_data.json` — данные узлов и связей
2. `network/index.html` — интерактивный D3-граф

Использование:
  python scripts/build_network.py                 # порог по умолчанию: 5
  python scripts/build_network.py --мин-вес 10    # выше порог -> меньше рёбер
  python scripts/build_network.py --лимит 100     # только лимит-N узлов
"""

import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from utils import (
    ДИРЕКТОРИЯ_ОТЧЁТОВ, настроить_вывод,
    классифицировать_викилинк, ЦВЕТА_КАТЕГОРИЙ, МЕТКИ_КАТЕГОРИЙ, ШАБЛОН_ТИКЕРА,
    разделить_перед_финансами, извлечь_викилинки,
)

КОРЕНЬ_ПРОЕКТА = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ДИРЕКТОРИЯ_СЕТИ = os.path.join(КОРЕНЬ_ПРОЕКТА, "network")


def сканировать_граф(минимальный_вес=5, лимит_узлов=None):
    """Собирает граф совместной встречаемости викилинков."""
    число_упоминаний_узлов = defaultdict(int)
    викилинки_по_файлу = {}

    for root, dirs, files in os.walk(ДИРЕКТОРИЯ_ОТЧЁТОВ):
        for f in files:
            if not f.endswith(".md"):
                continue
            m = re.match(rf"^({ШАБЛОН_ТИКЕРА})", f, re.IGNORECASE)
            if not m:
                continue
            with open(os.path.join(root, f), "r", encoding="utf-8") as fh:
                content = fh.read()
            split_parts = разделить_перед_финансами(content)
            if split_parts:
                content = split_parts[0]
            wls = set(извлечь_викилинки(content))
            викилинки_по_файлу[m.group(1)] = wls
            for wl in wls:
                число_упоминаний_узлов[wl] += 1

    if лимит_узлов:
        ведущие_узлы = set(
            имя for имя, _ in sorted(число_упоминаний_узлов.items(), key=lambda x: -x[1])[:лимит_узлов]
        )
    else:
        ведущие_узлы = set(имя for имя, count in число_упоминаний_узлов.items() if count >= 2)

    рёбра = defaultdict(int)
    for тикер, wls in викилинки_по_файлу.items():
        filtered = sorted(wls & ведущие_узлы)
        for i in range(len(filtered)):
            for j in range(i + 1, len(filtered)):
                рёбра[(filtered[i], filtered[j])] += 1

    отфильтрованные_рёбра = {k: v for k, v in рёбра.items() if v >= минимальный_вес}

    активные_узлы = set()
    for (a, b) in отфильтрованные_рёбра:
        активные_узлы.add(a)
        активные_узлы.add(b)

    узлы = []
    for имя in активные_узлы:
        cat = классифицировать_викилинк(имя)
        узлы.append({
            "имя": имя,
            "упоминания": число_упоминаний_узлов[имя],
            "категория": cat,
            "метка_категории": МЕТКИ_КАТЕГОРИЙ[cat],
            "цвет": ЦВЕТА_КАТЕГОРИЙ[cat],
        })

    список_рёбер = []
    for (источник, цель), вес in отфильтрованные_рёбра.items():
        список_рёбер.append({
            "источник": источник,
            "цель": цель,
            "вес": вес,
        })

    return узлы, список_рёбер


def построить_html(узлы, связи):
    """Генерирует автономную HTML-визуализацию на D3.js."""
    json_графа = json.dumps({"узлы": узлы, "связи": связи}, ensure_ascii=False)

    элементы_легенды = "".join(
        f'<div style="display:flex;align-items:center;margin:4px 12px">'
        f'<div style="width:14px;height:14px;border-radius:50%;background:{color};margin-right:6px"></div>'
        f'<span style="font-size:13px">{label}</span></div>'
        for cat, (color, label) in {
            k: (ЦВЕТА_КАТЕГОРИЙ[k], МЕТКИ_КАТЕГОРИЙ[k]) for k in ЦВЕТА_КАТЕГОРИЙ
        }.items()
    )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<title>Граф викилинков покрытия</title>
<style>
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #1a1a2e; color: #eee; overflow: hidden; }}
  #controls {{ position: fixed; top: 12px; left: 12px; z-index: 10; background: rgba(26,26,46,0.95); padding: 16px; border-radius: 10px; border: 1px solid #333; }}
  #controls h2 {{ font-size: 16px; margin-bottom: 8px; }}
  #controls label {{ font-size: 13px; display: block; margin: 6px 0 2px; }}
  #controls input[type=range] {{ width: 180px; }}
  #controls input[type=text] {{ width: 180px; padding: 4px 8px; background: #2a2a4e; border: 1px solid #444; color: #eee; border-radius: 4px; }}
  #legend {{ position: fixed; bottom: 12px; left: 12px; z-index: 10; background: rgba(26,26,46,0.95); padding: 12px; border-radius: 10px; border: 1px solid #333; display: flex; flex-wrap: wrap; }}
  #tooltip {{ position: fixed; background: rgba(0,0,0,0.9); color: #fff; padding: 8px 14px; border-radius: 6px; font-size: 13px; pointer-events: none; display: none; z-index: 20; border: 1px solid #555; }}
  #stats {{ position: fixed; top: 12px; right: 12px; z-index: 10; background: rgba(26,26,46,0.95); padding: 12px 16px; border-radius: 10px; border: 1px solid #333; font-size: 13px; }}
  svg {{ width: 100vw; height: 100vh; }}
</style>
</head>
<body>
<div id="controls">
  <h2>Граф викилинков</h2>
  <label>Мин. вес связи: <span id="weightVal">5</span></label>
  <input type="range" id="weightSlider" min="1" max="50" value="5">
  <label>Поиск:</label>
  <input type="text" id="search" placeholder="например, Газпром, Сбер, Яндекс">
</div>
<div id="legend">{элементы_легенды}</div>
<div id="tooltip"></div>
<div id="stats"></div>
<svg></svg>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const fullData = {json_графа};

// Сопоставление русских ключей JSON во внутренние английские для D3.js
fullData.узлы.forEach(n => {{
  n.id = n.имя; n.count = n.упоминания;
  n.category_label = n.метка_категории; n.color = n.цвет;
}});
fullData.связи.forEach(l => {{
  l.source = l.источник; l.target = l.цель; l.weight = l.вес;
}});
fullData.nodes = fullData.узлы;
fullData.links = fullData.связи;
const width = window.innerWidth, height = window.innerHeight;

const svg = d3.select("svg");
const g = svg.append("g");

  // Масштабирование
svg.call(d3.zoom().scaleExtent([0.1, 8]).on("zoom", (e) => g.attr("transform", e.transform)));

const tooltip = d3.select("#tooltip");
let simulation, linkG, nodeG, labelG;

function render(minWeight) {{
  const links = fullData.links.filter(l => l.weight >= minWeight);
  const activeIds = new Set();
  links.forEach(l => {{ activeIds.add(l.source.id || l.source); activeIds.add(l.target.id || l.target); }});
  const nodes = fullData.nodes.filter(n => activeIds.has(n.id));

  d3.select("#stats").html(`Узлы: ${{nodes.length}} | Связи: ${{links.length}}`);

  g.selectAll("*").remove();

  // Масштаб
  const maxCount = d3.max(nodes, d => d.count) || 1;
  const rScale = d3.scaleSqrt().domain([1, maxCount]).range([4, 40]);
  const maxWeight = d3.max(links, l => l.weight) || 1;
  const wScale = d3.scaleLinear().domain([minWeight, maxWeight]).range([0.5, 4]);
  const oScale = d3.scaleLinear().domain([minWeight, maxWeight]).range([0.15, 0.6]);

  simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(80).strength(0.3))
    .force("charge", d3.forceManyBody().strength(-150))
    .force("center", d3.forceCenter(width / 2, height / 2))
    .force("collision", d3.forceCollide().radius(d => rScale(d.count) + 2));

  linkG = g.append("g").selectAll("line").data(links).join("line")
    .attr("stroke", "#555").attr("stroke-opacity", d => oScale(d.weight))
    .attr("stroke-width", d => wScale(d.weight));

  nodeG = g.append("g").selectAll("circle").data(nodes).join("circle")
    .attr("r", d => rScale(d.count)).attr("fill", d => d.color)
    .attr("stroke", "#fff").attr("stroke-width", 0.5).attr("opacity", 0.9)
    .call(d3.drag().on("start", dragStart).on("drag", dragging).on("end", dragEnd))
    .on("mouseover", (e, d) => {{
      tooltip.style("display", "block").html(
        `<b>${{d.id}}</b><br>Упоминаний: ${{d.count}}<br>Категория: ${{d.category_label}}`
      );
      highlightNeighbors(d);
    }})
    .on("mousemove", (e) => tooltip.style("left", e.pageX+12+"px").style("top", e.pageY-20+"px"))
    .on("mouseout", () => {{ tooltip.style("display", "none"); resetHighlight(); }});

  labelG = g.append("g").selectAll("text").data(nodes.filter(d => d.count >= 20)).join("text")
    .text(d => d.id).attr("font-size", d => Math.max(8, Math.min(14, rScale(d.count) * 0.7)))
    .attr("fill", "#ccc").attr("text-anchor", "middle").attr("dy", d => rScale(d.count) + 12)
    .style("pointer-events", "none");

  simulation.on("tick", () => {{
    linkG.attr("x1", d=>d.source.x).attr("y1", d=>d.source.y).attr("x2", d=>d.target.x).attr("y2", d=>d.target.y);
    nodeG.attr("cx", d=>d.x).attr("cy", d=>d.y);
    labelG.attr("x", d=>d.x).attr("y", d=>d.y);
  }});
}}

function highlightNeighbors(d) {{
  const neighbors = new Set();
  linkG.each(function(l) {{
    if (l.source.id === d.id) neighbors.add(l.target.id);
    if (l.target.id === d.id) neighbors.add(l.source.id);
  }});
  neighbors.add(d.id);
  nodeG.attr("opacity", n => neighbors.has(n.id) ? 1 : 0.1);
  linkG.attr("stroke-opacity", l => (l.source.id===d.id||l.target.id===d.id) ? 0.8 : 0.03);
  labelG.attr("opacity", n => neighbors.has(n.id) ? 1 : 0.1);
}}

function resetHighlight() {{
  nodeG.attr("opacity", 0.9);
  linkG.attr("stroke-opacity", d => 0.3);
  labelG.attr("opacity", 1);
}}

function dragStart(e, d) {{ if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; }}
function dragging(e, d) {{ d.fx = e.x; d.fy = e.y; }}
function dragEnd(e, d) {{ if (!e.active) simulation.alphaTarget(0); d.fx = null; d.fy = null; }}

  // Управление
d3.select("#weightSlider").on("input", function() {{
  const v = +this.value;
  d3.select("#weightVal").text(v);
  render(v);
}});

d3.select("#search").on("input", function() {{
  const q = this.value.toLowerCase();
  if (!q) {{ resetHighlight(); return; }}
  const match = fullData.nodes.find(n => n.id.toLowerCase().includes(q));
  if (match) highlightNeighbors(match);
}});

  // Первичная отрисовка
render(5);
</script>
</body>
</html>"""


def main():
    настроить_вывод()

    args = sys.argv[1:]
    минимальный_вес = 2
    лимит_узлов = None

    for i, arg in enumerate(args):
        if arg == "--мин-вес" and i + 1 < len(args):
            минимальный_вес = int(args[i + 1])
        elif arg == "--лимит" and i + 1 < len(args):
            лимит_узлов = int(args[i + 1])

    os.makedirs(ДИРЕКТОРИЯ_СЕТИ, exist_ok=True)

    print(f"Сканирую совместную встречаемость викилинков (мин. вес: {минимальный_вес})...")
    узлы, рёбра = сканировать_граф(минимальный_вес=минимальный_вес, лимит_узлов=лимит_узлов)
    print(f"Граф: узлов {len(узлы)}, связей {len(рёбра)}")

    данные_графа = {"узлы": узлы, "связи": рёбра}
    json_path = os.path.join(ДИРЕКТОРИЯ_СЕТИ, "graph_data.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(данные_графа, f, ensure_ascii=False, indent=2)
    print(f"Сохранён файл: {json_path}")

    html = построить_html(узлы, рёбра)
    html_path = os.path.join(ДИРЕКТОРИЯ_СЕТИ, "index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Сохранён файл: {html_path}")

    print(f"\nОткройте в браузере: {html_path}")
    print("Или поднимите местный сервер: python -m http.server 8000 --directory network/")


if __name__ == "__main__":
    main()

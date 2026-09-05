/* Markdown renderer using DOM nodes only: imported HTML never executes. */
(() => {
  function inline(parent, text) {
    const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\[\[[^\]]+\]\])/g;
    let start = 0;
    for (const match of text.matchAll(pattern)) {
      parent.append(document.createTextNode(text.slice(start, match.index)));
      const token = match[0],
        node = document.createElement(
          token.startsWith("`")
            ? "code"
            : token.startsWith("**")
              ? "strong"
              : "span",
        );
      node.textContent = token.startsWith("`")
        ? token.slice(1, -1)
        : token.startsWith("**")
          ? token.slice(2, -2)
          : token.slice(2, -2).split("|").at(-1);
      if (token.startsWith("[[")) node.className = "wiki";
      parent.append(node);
      start = match.index + token.length;
    }
    parent.append(document.createTextNode(text.slice(start)));
  }
  function render(markdown, target) {
    target.replaceChildren();
    const text = String(markdown || "").replace(
      /^---\r?\n[\s\S]*?\r?\n---\r?\n/,
      "",
    );
    const lines = text.replace(/\r/g, "").split("\n");
    let lists = [],
      code = null,
      table = null;
    for (let i = 0; i < lines.length; i++) {
      const line = lines[i];
      if (/^\s*```/.test(line)) {
        lists = [];
        table = null;
        if (code) {
          code = null;
        } else {
          const pre = document.createElement("pre");
          code = document.createElement("code");
          pre.append(code);
          target.append(pre);
        }
        continue;
      }
      if (code) {
        code.append(document.createTextNode(line + "\n"));
        continue;
      }
      if (!line.trim()) {
        lists = [];
        table = null;
        continue;
      }
      const heading = /^(#{1,6})\s+(.+)$/.exec(line);
      if (heading) {
        lists = [];
        table = null;
        const h = document.createElement("h" + heading[1].length);
        inline(h, heading[2]);
        target.append(h);
        continue;
      }
      if (/^\s*([-*_])\1\1+\s*$/.test(line)) {
        lists = [];
        target.append(document.createElement("hr"));
        continue;
      }
      const item = /^(\s*)(?:[-+*]|\d+\.)\s+(.*)$/.exec(line);
      if (item) {
        table = null;
        const depth = item[1].replace(/\t/g, "    ").length;
        while (lists.length && lists.at(-1).depth > depth) lists.pop();
        if (!lists.length || lists.at(-1).depth < depth) {
          const ul = document.createElement("ul");
          (lists.at(-1)?.last || target).append(ul);
          lists.push({ depth, ul, last: null });
        }
        const li = document.createElement("li");
        inline(li, item[2]);
        lists.at(-1).ul.append(li);
        lists.at(-1).last = li;
        continue;
      }
      lists = [];
      if (
        line.includes("|") &&
        (table || /^\s*\|?\s*:?-{3}/.test(lines[i + 1] || ""))
      ) {
        if (!table) {
          table = document.createElement("table");
          target.append(table);
        }
        if (/^\s*\|?[\s:|-]+$/.test(line)) continue;
        const tr = document.createElement("tr");
        const header = table.childElementCount === 0;
        for (const cell of line.replace(/^\s*\||\|\s*$/g, "").split("|")) {
          const td = document.createElement(header ? "th" : "td");
          inline(td, cell.trim());
          tr.append(td);
        }
        table.append(tr);
        continue;
      }
      table = null;
      const p = document.createElement(
        line.startsWith(">") ? "blockquote" : "p",
      );
      inline(p, line.replace(/^>\s?/, ""));
      target.append(p);
    }
  }
  globalThis.NoteMarkdown = { render };
})();

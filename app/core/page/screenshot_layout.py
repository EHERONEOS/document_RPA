"""内部滚动页面的临时截图布局，只展开指定内容区域及其祖先。"""

EXPAND_LAYOUT = """
const key = arguments[0];
const form = document.querySelector(arguments[1]);
if (!form) return false;
const entries = [];
for (let node = form; node; node = node.parentElement) {
    entries.push({node, style: node.getAttribute('style'),
                  top: node.scrollTop, left: node.scrollLeft});
}
// 先保存全部状态，再修改；中途异常也能由 finally 恢复。
window[key] = entries;
for (const {node} of entries) {
    node.style.setProperty('height', 'auto', 'important');
    node.style.setProperty('max-height', 'none', 'important');
    node.style.setProperty('overflow', 'visible', 'important');
    node.style.setProperty('flex-shrink', '0', 'important');
    node.style.setProperty('scroll-behavior', 'auto', 'important');
    node.scrollTop = 0;
    node.scrollLeft = 0;
}
// 强制完成布局，确保 full_page 按展开后的文档高度截图。
return document.documentElement.scrollHeight;
"""

RESTORE_LAYOUT = """
const key = arguments[0];
const entries = window[key];
if (!entries) return;
for (const {node, style} of entries) {
    if (style === null) node.removeAttribute('style');
    else node.setAttribute('style', style);
}
void document.documentElement.offsetHeight;
for (const {node, top, left} of [...entries].reverse()) {
    node.scrollTo({top, left, behavior: 'instant'});
}
delete window[key];
"""

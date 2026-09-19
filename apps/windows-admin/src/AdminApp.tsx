import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";
import { ApiError, createLibrary, deleteLibrary, getSession, loadDirectories, loadDrives, loadHealth, loadLibraries, updateLibrary, validatePath } from "./api";
import type { Health, Library } from "./api";
import "./styles.css";

type DialogMode = "create" | "edit" | null;
type FormState = { id?: string; name: string; path: string; recursive: boolean; enabled: boolean };
const emptyForm: FormState = { name: "", path: "", recursive: true, enabled: true };

function generatedLibraryId(name: string) {
  const base = name.toLocaleLowerCase().normalize("NFKD").replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "library";
  return `${base}-${Math.random().toString(36).slice(2, 10)}`;
}

function readableError(prefix: string, error: unknown) {
  return `${prefix}：${error instanceof ApiError ? error.message : "发生未知错误，请稍后重试。"}`;
}

export function AdminApp() {
  const [libraries, setLibraries] = useState<Library[]>([]);
  const [health, setHealth] = useState<Health | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [dialog, setDialog] = useState<DialogMode>(null);
  const [form, setForm] = useState<FormState>(emptyForm);
  const [saving, setSaving] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<Library | null>(null);
  const refreshLibraries = async () => {
    try {
      setError("");
      setLibraries(await loadLibraries());
    } catch (cause) {
      setError(readableError("图片目录加载失败", cause));
    }
  };
  useEffect(() => {
    let active = true;
    (async () => {
      try {
        await getSession();
        const [nextHealth, nextLibraries] = await Promise.all([loadHealth(), loadLibraries()]);
        if (active) { setHealth(nextHealth); setLibraries(nextLibraries); }
      } catch (cause) {
        if (active) setError(readableError("图片目录加载失败", cause));
      } finally {
        if (active) setLoading(false);
      }
    })();
    return () => { active = false; };
  }, []);
  const comfyOnline = health?.comfyui?.status === "online";
  const openCreate = () => { setForm(emptyForm); setDialog("create"); };
  const openEdit = (library: Library) => { setForm(library); setDialog("edit"); };
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!form.name.trim() || !form.path.trim()) return;
    setSaving(true);
    try {
      const payload = { name: form.name.trim(), path: form.path.trim(), recursive: form.recursive, enabled: form.enabled };
      if (dialog === "edit" && form.id) await updateLibrary(form.id, payload);
      else await createLibrary({ ...payload, id: generatedLibraryId(payload.name) });
      setDialog(null);
      await refreshLibraries();
    } catch (cause) {
      setError(readableError("目录保存失败", cause));
    } finally { setSaving(false); }
  };
  const toggle = async (library: Library) => {
    try { await updateLibrary(library.id, { enabled: !library.enabled }); await refreshLibraries(); }
    catch (cause) { setError(readableError("目录状态更新失败", cause)); }
  };
  const remove = async () => {
    if (!deleteTarget) return;
    try { await deleteLibrary(deleteTarget.id); setDeleteTarget(null); await refreshLibraries(); }
    catch (cause) { setError(readableError("目录删除失败", cause)); }
  };
  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><span className="brand-mark">R</span><div><strong>Remote ComfyUI</strong><small>本机管理</small></div></div>
      <nav aria-label="主导航"><button className="nav-item active" type="button">概览</button><button className="nav-item" type="button" onClick={() => document.getElementById("libraries")?.scrollIntoView()}>图片目录</button></nav>
      <div className="sidebar-footer">Gateway · 127.0.0.1:3001</div>
    </aside>
    <main className="content">
      <header className="page-header"><div><p className="eyebrow">管理控制台</p><h1>本机资源</h1><p className="subtitle">管理 ComfyUI 可使用的图片目录与连接状态。</p></div><button className="primary" type="button" onClick={openCreate}>＋ 新增目录</button></header>
      {error && <div role="alert" className="alert"><span>{error}</span><button type="button" aria-label="关闭错误" onClick={() => setError("")}>×</button></div>}
      <section aria-labelledby="overview-heading"><div className="section-heading"><h2 id="overview-heading">状态概览</h2><span className="muted">实时检查</span></div><div className="status-grid"><div className="status-card"><span className="status-label">Gateway</span><strong className="status-value"><i className="dot online" />运行中</strong><small>本机服务正常</small></div><div className="status-card"><span className="status-label">ComfyUI</span><strong className="status-value" role="status"><i className={`dot ${comfyOnline ? "online" : "offline"}`} />{health ? (comfyOnline ? "ComfyUI 在线" : "ComfyUI 离线") : "检查中…"}</strong><small>{health?.comfyui?.version ? `版本 ${health.comfyui.version}` : "请检查 ComfyUI 服务"}</small></div><div className="status-card"><span className="status-label">图片目录</span><strong className="status-value">{libraries.length}<small className="inline-muted"> 个配置</small></strong><small>{libraries.filter((item) => item.enabled).length} 个已启用</small></div></div></section>
      <section id="libraries" aria-labelledby="libraries-heading" className="libraries-section"><div className="section-heading"><div><h2 id="libraries-heading">图片目录</h2><p className="section-description">目录配置只保存路径，不会移动或删除原始图片。</p></div><button className="secondary" type="button" onClick={openCreate}>新增目录</button></div>{loading ? <div className="empty-state">正在加载目录…</div> : libraries.length === 0 ? <div className="empty-state"><div className="empty-icon">▧</div><strong>还没有配置图片目录</strong><p>添加一个本机文件夹，让工作流可以使用其中的图片。</p><button className="primary" type="button" onClick={openCreate}>新增第一个目录</button></div> : <div className="table-wrap"><table><thead><tr><th>名称</th><th>路径</th><th>扫描方式</th><th>状态</th><th><span className="sr-only">操作</span></th></tr></thead><tbody>{libraries.map((library) => <tr key={library.id}><td><strong>{library.name}</strong><small className="id-label">{library.id}</small></td><td className="path-cell" title={library.path}>{library.path}</td><td>{library.recursive ? "包含子目录" : "仅当前目录"}</td><td><span className={`badge ${library.enabled ? "enabled" : "disabled"}`}>{library.enabled ? "已启用" : "已停用"}</span></td><td><div className="actions"><button type="button" aria-label={`${library.enabled ? "停用" : "启用"} ${library.name}`} onClick={() => toggle(library)}>{library.enabled ? "停用" : "启用"}</button><button type="button" aria-label={`编辑 ${library.name}`} onClick={() => openEdit(library)}>编辑</button><button type="button" className="danger-link" aria-label={`删除 ${library.name}`} onClick={() => setDeleteTarget(library)}>删除</button></div></td></tr>)}</tbody></table></div>}</section>
    </main>
    {dialog && <LibraryDialog mode={dialog} form={form} setForm={setForm} saving={saving} onClose={() => setDialog(null)} onSubmit={submit} />}
    {deleteTarget && <div className="modal-backdrop"><section className="dialog compact" role="dialog" aria-modal="true" aria-labelledby="delete-heading"><h2 id="delete-heading">确认删除</h2><p>确定要删除“{deleteTarget.name}”吗？</p><p className="warning">仅删除目录配置，不会删除原图。</p><div className="dialog-actions"><button type="button" className="secondary" onClick={() => setDeleteTarget(null)}>取消</button><button type="button" className="danger" onClick={remove}>确认删除</button></div></section></div>}
  </div>;
}

function LibraryDialog({ mode, form, setForm, saving, onClose, onSubmit }: { mode: Exclude<DialogMode, null>; form: FormState; setForm: (value: FormState) => void; saving: boolean; onClose: () => void; onSubmit: (event: FormEvent) => void }) {
  const [drives, setDrives] = useState<string[]>([]);
  const [directories, setDirectories] = useState<string[]>([]);
  const [browseError, setBrowseError] = useState("");
  const [expanded, setExpanded] = useState<string[]>([]);
  const browse = async (path: string) => {
    try { setBrowseError(""); setExpanded((previous) => previous.includes(path) ? previous.filter((item) => item !== path) : [...previous, path]); setDirectories(await loadDirectories(path)); }
    catch (cause) { setBrowseError(readableError("目录浏览失败", cause)); }
  };
  useEffect(() => { loadDrives().then(setDrives).catch((cause) => setBrowseError(readableError("磁盘读取失败", cause))); }, []);
  const choose = async (path: string) => {
    try { setForm({ ...form, path: await validatePath(path) }); }
    catch (cause) { setBrowseError(readableError("目录验证失败", cause)); }
  };
  return <div className="modal-backdrop"><section className="dialog" role="dialog" aria-modal="true" aria-labelledby="library-dialog-heading"><div className="dialog-header"><div><p className="eyebrow">图片目录</p><h2 id="library-dialog-heading">{mode === "create" ? "新增图片目录" : "编辑图片目录"}</h2></div><button type="button" className="close-button" aria-label="关闭弹窗" onClick={onClose}>×</button></div><form onSubmit={onSubmit}><label>目录名称<input aria-label="目录名称" value={form.name} onChange={(event) => setForm({ ...form, name: event.target.value })} required autoFocus /></label><label>目录路径<input aria-label="目录路径" value={form.path} onChange={(event) => setForm({ ...form, path: event.target.value })} placeholder="例如 C:\\Pictures" required /></label><div className="folder-picker"><div className="picker-heading"><strong>选择文件夹</strong><span>固定磁盘及直属子目录</span></div>{browseError && <p className="picker-error" role="alert">{browseError}</p>}<div className="tree">{drives.map((drive) => <div key={drive}><button type="button" className="tree-item" aria-label={drive} onClick={() => browse(drive)} aria-expanded={expanded.includes(drive)}><span aria-hidden="true">{expanded.includes(drive) ? "⌄" : "›"}</span>{drive}</button>{expanded.includes(drive) && <div className="tree-children">{directories.map((directory) => <button type="button" className="tree-item" aria-label={directory} key={directory} onClick={() => choose(directory)}>{directory}</button>)}</div>}</div>)}</div></div><label className="check-row"><input type="checkbox" checked={form.recursive} onChange={(event) => setForm({ ...form, recursive: event.target.checked })} />包含所有子目录</label><div className="dialog-actions"><button type="button" className="secondary" onClick={onClose}>取消</button><button className="primary" type="submit" disabled={saving || !form.name.trim() || !form.path.trim()}>{saving ? "保存中…" : "保存目录"}</button></div></form></section></div>;
}

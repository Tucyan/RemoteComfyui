import { useEffect, useMemo, useRef, useState } from "react";
import * as FileSystem from "expo-file-system/legacy";
import * as ImagePicker from "expo-image-picker";
import * as MediaLibrary from "expo-media-library";
import * as Sharing from "expo-sharing";
import { useVideoPlayer, VideoView } from "expo-video";
import { StatusBar } from "expo-status-bar";
import {
  ActivityIndicator,
  Alert,
  Image,
  KeyboardAvoidingView,
  Modal,
  Platform,
  Pressable,
  SafeAreaView,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { RemoteApi, type Artifact, type GenerationJob, type Library, type LibraryImage } from "./src/api/client";
import { ReferenceImageStrip, type ReferenceItem } from "./src/components/ReferenceImageStrip";
import { ImageSettings, type EditImageSettingsDraft, type T2IImageSettingsDraft } from "./src/components/ImageSettings";
import { VideoSettings, type VideoDraft } from "./src/components/VideoSettings";
import { WorkflowPicker } from "./src/components/WorkflowPicker";
import { ZoomableImage } from "./src/components/ZoomableImage";
import { libraryReferenceSources, phoneReferenceSources } from "./src/domain/referenceImages";
import {
  insertPictureToken,
  calculateVideoDimensions,
  formatElapsed,
  updateWorkflowPrompt,
  updateWorkflowValue,
  moveReference,
  normalizeReferences,
  renumberPictureTokens,
  validateReferenceCount,
  validateVideoSettings,
  calculateEditDimensions,
  initialEditScale,
  lockEditDimensions,
  calculateImageDimensions,
  normalizeImageDimensions,
  WORKFLOW_DESCRIPTORS,
  type WorkflowId,
} from "./src/domain/draft";
import { PairingStore, type PairingDetails } from "./src/storage/pairing";

type Tab = "generate" | "tasks" | "artifacts" | "library" | "settings";
type Ref = ReferenceItem & { assetId: string };

const pairingStore = new PairingStore();

export default function App() {
  const [pairing, setPairing] = useState<PairingDetails | null | undefined>(undefined);
  const [api, setApi] = useState<RemoteApi | null>(null);

  useEffect(() => {
    pairingStore.load().then((saved) => {
      setPairing(saved);
      if (saved) setApi(new RemoteApi(saved.baseUrl, saved.token));
    });
  }, []);

  if (pairing === undefined) return <Centered><ActivityIndicator color="#1769aa" /></Centered>;
  if (!pairing || !api) return <PairScreen onPaired={async (details) => { await pairingStore.save(details); setPairing(details); setApi(new RemoteApi(details.baseUrl, details.token)); }} />;
  return <Workspace api={api} pairing={pairing} onUnpair={async () => { await pairingStore.clear(); setPairing(null); setApi(null); }} />;
}

function PairScreen({ onPaired }: { onPaired: (details: PairingDetails) => Promise<void> }) {
  const [baseUrl, setBaseUrl] = useState("http://127.0.0.1:3000");
  const [code, setCode] = useState("");
  const [deviceName, setDeviceName] = useState("Android 手机");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function pair() {
    setError("");
    if (!/^https?:\/\/[^\s]+$/i.test(baseUrl.trim()) || !/^\d{6}$/.test(code.trim())) {
      setError("请输入电脑的 Gateway 地址和 6 位配对码");
      return;
    }
    setBusy(true);
    try {
      const result = await new RemoteApi(baseUrl.trim()).pair(code.trim(), deviceName.trim() || "Android 手机");
      await onPaired({ baseUrl: baseUrl.trim(), token: result.token, deviceName: deviceName.trim() || "Android 手机" });
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "配对失败，请检查地址和配对码");
    } finally {
      setBusy(false);
    }
  }

  return <SafeAreaView style={styles.safe}><StatusBar style="dark" /><KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : undefined} style={styles.centerContent}>
    <View style={styles.pairPanel}>
      <Text style={styles.brand}>Remote ComfyUI</Text>
      <Text style={styles.subtitle}>连接电脑上的固定工作流</Text>
      <Text style={styles.fieldLabel}>Gateway 地址</Text>
      <TextInput autoCapitalize="none" autoCorrect={false} keyboardType="url" value={baseUrl} onChangeText={setBaseUrl} placeholder="http://电脑IP:3000" style={styles.input} />
      <Text style={styles.fieldLabel}>配对码</Text>
      <TextInput keyboardType="number-pad" maxLength={6} value={code} onChangeText={setCode} placeholder="管理页显示的 6 位数字" style={styles.input} />
      <Text style={styles.fieldLabel}>设备名称</Text>
      <TextInput value={deviceName} onChangeText={setDeviceName} style={styles.input} />
      {error ? <Text style={styles.error}>{error}</Text> : null}
      <PrimaryButton title={busy ? "连接中..." : "配对并进入"} onPress={pair} disabled={busy} />
      <Text style={styles.hint}>手机和电脑需要连接同一个局域网。模拟器可使用 adb reverse 访问本机 Gateway。</Text>
    </View>
  </KeyboardAvoidingView></SafeAreaView>;
}

function Workspace({ api, pairing, onUnpair }: { api: RemoteApi; pairing: PairingDetails; onUnpair: () => Promise<void> }) {
  const [tab, setTab] = useState<Tab>("generate");
  const [librarySelectionMode, setLibrarySelectionMode] = useState(false);
  const [workflow, setWorkflow] = useState<WorkflowId>("qwen_edit_2511");
  const [prompts, setPrompts] = useState<Record<WorkflowId, string>>({ qwen_edit_2511: "", qwen_image_2_1_8gb_edit: "", qwen_image_2_1_8gb_t2i: "", minimax_h3: "" });
  const prompt = prompts[workflow];
  const setPrompt = (value: string | ((previous: string) => string)) => setPrompts((previous) => updateWorkflowPrompt(previous, workflow, typeof value === "function" ? value(previous[workflow]) : value));
  const [referencesByWorkflow, setReferencesByWorkflow] = useState<Record<WorkflowId, Ref[]>>({ qwen_edit_2511: [], qwen_image_2_1_8gb_edit: [], qwen_image_2_1_8gb_t2i: [], minimax_h3: [] });
  const references = referencesByWorkflow[workflow];
  const [videoDraft, setVideoDraft] = useState<VideoDraft>({ ratio: "9:16", quality: 0.4, custom: false, width: "480", height: "864", frames: "124" });
  const [editDraft, setEditDraft] = useState<EditImageSettingsDraft>({ editSizeMode: "scale", sizeAnchor: "width", scaleFactor: 1, width: "", height: "" });
  const [t2iDraft, setT2iDraft] = useState<T2IImageSettingsDraft>({ ratio: "1:1", quality: 1, custom: false, width: "1024", height: "1024" });
  const [jobs, setJobs] = useState<GenerationJob[]>([]);
  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const importingLibrary = useRef(false);
  const uploadingReferences = useRef(false);
  const replaceReferences = (next: Ref[]) => {
    const previous = references;
    setReferencesByWorkflow((current) => updateWorkflowValue(current, workflow, next));
    setPrompts((current) => ({ ...current, [workflow]: renumberPictureTokens(current[workflow], next.map((item) => item.assetId)) }));
    if (workflow === "qwen_image_2_1_8gb_edit" && previous[0]?.assetId !== next[0]?.assetId && next[0]?.width && next[0]?.height) {
      const scaleFactor = initialEditScale(next[0].width, next[0].height);
      try {
        const dimensions = calculateEditDimensions(next[0].width, next[0].height, scaleFactor);
        setEditDraft({ editSizeMode: "scale", sizeAnchor: "width", scaleFactor, width: String(dimensions.width), height: String(dimensions.height) });
      } catch {
        const anchor = next[0].width >= next[0].height ? "width" : "height";
        const dimensions = lockEditDimensions(next[0].width, next[0].height, anchor, 2048);
        setEditDraft({ editSizeMode: "dimensions", sizeAnchor: anchor, scaleFactor, width: String(dimensions.width), height: String(dimensions.height) });
      }
    }
  };

  const refreshJobs = async () => { try { setJobs((await api.listJobs()).jobs); } catch (cause) { setMessage(errorText(cause)); } };
  const refreshArtifacts = async () => { try { setArtifacts((await api.listArtifacts()).artifacts); } catch (cause) { setMessage(errorText(cause)); } };

  useEffect(() => {
    refreshJobs();
    refreshArtifacts();
    const timer = setInterval(refreshJobs, 5000);
    return () => clearInterval(timer);
  }, [api]);

  async function pickReferences() {
    if (uploadingReferences.current || busy) return;
    const maximum = WORKFLOW_DESCRIPTORS[workflow].maxReferences;
    const remaining = maximum - references.length;
    if (remaining <= 0) { setMessage(maximum === 0 ? "当前工作流不使用参考图" : `当前工作流最多 ${maximum} 张参考图`); return; }
    uploadingReferences.current = true;
    setBusy(true); setMessage("");
    try {
      const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsMultipleSelection: true, selectionLimit: remaining, quality: 0.95 });
      if (result.canceled) return;
      const uploaded = await api.uploadImages(result.assets.map((asset, index) => ({ uri: asset.uri, name: asset.fileName || `reference-${index + 1}.jpg`, type: asset.mimeType || "image/jpeg" })));
      const next = uploaded.assets.map((asset, index) => ({ id: asset.id, assetId: asset.id, name: asset.filename, ...phoneReferenceSources(result.assets[index].uri), width: asset.width, height: asset.height }));
      replaceReferences([...references, ...next]);
    } catch (cause) { setMessage(errorText(cause)); } finally { uploadingReferences.current = false; setBusy(false); }
  }

  async function submit() {
    setMessage("");
    const refs = normalizeReferences(references.map((item) => item.assetId));
    if (!prompt.trim()) { setMessage("请先输入提示词"); return; }
    if (!validateReferenceCount(workflow, refs.length)) {
      const descriptor = WORKFLOW_DESCRIPTORS[workflow];
      setMessage(descriptor.minReferences === 0 ? "当前工作流不接受参考图" : `请添加 ${descriptor.minReferences}-${descriptor.maxReferences} 张参考图`);
      return;
    }
    setBusy(true);
    try {
      if (workflow === "minimax_h3") {
        const calculated = calculateVideoDimensions(videoDraft.ratio, videoDraft.quality);
        const width = videoDraft.custom ? Number(videoDraft.width) : calculated.width;
        const height = videoDraft.custom ? Number(videoDraft.height) : calculated.height;
        const frames = Number(videoDraft.frames);
        const settings = validateVideoSettings(width, height, frames);
        if (!settings.ok) { setMessage(settings.error); return; }
        await api.createVideoJob(prompt.trim(), refs, settings.width, settings.height, frames);
      } else if (workflow === "qwen_edit_2511") {
        await api.createImageJob({ prompt: prompt.trim(), workflow, referenceAssetIds: refs });
      } else if (workflow === "qwen_image_2_1_8gb_edit") {
        const first = references[0];
        if (!first?.width || !first?.height) { setMessage("无法读取首张参考图的尺寸，请重新添加图片"); return; }
        if (editDraft.editSizeMode === "scale") {
          await api.createImageJob({ prompt: prompt.trim(), workflow, referenceAssetIds: refs, editSizeMode: "scale", scaleFactor: editDraft.scaleFactor });
        } else {
          const dimensions = editDraft[editDraft.sizeAnchor].trim()
            ? lockEditDimensions(first.width, first.height, editDraft.sizeAnchor, Number(editDraft[editDraft.sizeAnchor]))
            : null;
          const width = dimensions?.width ?? Number(editDraft.width);
          const height = dimensions?.height ?? Number(editDraft.height);
          if (!Number.isInteger(width) || !Number.isInteger(height) || width < 32 || height < 32 || width > 2048 || height > 2048 || width % 32 || height % 32) throw new Error("编辑尺寸必须为 32 的倍数，且在 32～2048 像素之间");
          await api.createImageJob({ prompt: prompt.trim(), workflow, referenceAssetIds: refs, editSizeMode: "dimensions", width, height });
        }
      } else {
        const calculated = calculateImageDimensions(t2iDraft.ratio, t2iDraft.quality);
        const dimensions = t2iDraft.custom
          ? normalizeImageDimensions(Number(t2iDraft.width), Number(t2iDraft.height))
          : calculated;
        await api.createImageJob({ prompt: prompt.trim(), workflow, referenceAssetIds: [], width: dimensions.width, height: dimensions.height });
      }
      setMessage("任务已进入队列");
      setTab("tasks");
      await refreshJobs();
    } catch (cause) { setMessage(errorText(cause)); } finally { setBusy(false); }
  }

  const currentRefs = references as ReferenceItem[];
  return <SafeAreaView style={styles.safe}><StatusBar style="dark" /><View style={styles.appShell}>
    <View style={styles.header}><View><Text style={styles.headerTitle}>Remote ComfyUI</Text><Text style={styles.headerSub}>{pairing.baseUrl}</Text></View><View style={styles.statusDot} /></View>
    <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
      {tab === "generate" && <GeneratePage workflow={workflow} setWorkflow={setWorkflow} prompt={prompt} setPrompt={(value) => setPrompt(renumberPictureTokens(value, references.map((item) => item.assetId)))} references={currentRefs} onPick={pickReferences} onPickLibrary={() => { setLibrarySelectionMode(true); setTab("library"); }} onMove={(from, to) => replaceReferences(moveReference(references, from, to))} onRemove={(index) => replaceReferences(references.filter((_, itemIndex) => itemIndex !== index))} onInsert={(index) => setPrompt((value) => insertPictureToken(value, index))} videoDraft={videoDraft} setVideoDraft={setVideoDraft} editDraft={editDraft} setEditDraft={setEditDraft} t2iDraft={t2iDraft} setT2iDraft={setT2iDraft} onSubmit={submit} busy={busy} message={message} />}
      {tab === "tasks" && <TasksPage jobs={jobs} onRefresh={refreshJobs} />}
      {tab === "artifacts" && <ArtifactsPage artifacts={artifacts} api={api} onRefresh={refreshArtifacts} />}
      {tab === "library" && <LibraryPage api={api} selectionMode={librarySelectionMode} importing={busy} onUse={async (image) => {
        if (importingLibrary.current) return;
        const maximum = WORKFLOW_DESCRIPTORS[workflow].maxReferences;
        if (maximum === 0 || references.length >= maximum) { setMessage(maximum === 0 ? "当前工作流不使用参考图" : `当前工作流最多 ${maximum} 张参考图`); setTab("generate"); return; }
        importingLibrary.current = true;
        setBusy(true); setMessage("");
        try {
          const uploaded = await api.importLibraryImage(image);
          replaceReferences([...references, { id: uploaded.id, assetId: uploaded.id, name: uploaded.filename, ...libraryReferenceSources(api, image), width: uploaded.width, height: uploaded.height }]);
          setTab("generate"); setMessage(`已加入 ${image.name}`);
        } catch (cause) { setMessage(errorText(cause)); setTab("generate"); } finally { importingLibrary.current = false; setBusy(false); }
      }} />}
      {tab === "settings" && <SettingsPage pairing={pairing} api={api} onUnpair={onUnpair} />}
    </ScrollView>
    <View style={styles.tabBar}>{([ ["generate", "生成"], ["tasks", "任务"], ["artifacts", "产物"], ["library", "图库"], ["settings", "设置"] ] as [Tab, string][]).map(([key, label]) => <Pressable key={key} onPress={() => { setLibrarySelectionMode(false); setTab(key); }} style={[styles.tab, tab === key && styles.tabActive]}><Text style={[styles.tabText, tab === key && styles.tabTextActive]}>{label}</Text></Pressable>)}</View>
  </View></SafeAreaView>;
}

function GeneratePage({ workflow, setWorkflow, prompt, setPrompt, references, onPick, onPickLibrary, onMove, onRemove, onInsert, videoDraft, setVideoDraft, editDraft, setEditDraft, t2iDraft, setT2iDraft, onSubmit, busy, message }: { workflow: WorkflowId; setWorkflow: (workflow: WorkflowId) => void; prompt: string; setPrompt: (value: string) => void; references: ReferenceItem[]; onPick: () => Promise<void>; onPickLibrary: () => void; onMove: (from: number, to: number) => void; onRemove: (index: number) => void; onInsert: (index: number) => void; videoDraft: VideoDraft; setVideoDraft: (value: VideoDraft) => void; editDraft: EditImageSettingsDraft; setEditDraft: (value: EditImageSettingsDraft) => void; t2iDraft: T2IImageSettingsDraft; setT2iDraft: (value: T2IImageSettingsDraft) => void; onSubmit: () => Promise<void>; busy: boolean; message: string }) {
  const descriptor = WORKFLOW_DESCRIPTORS[workflow];
  const usesReferences = descriptor.maxReferences > 0;
  return <View style={styles.page}><Text style={styles.pageTitle}>开始生成</Text><WorkflowPicker value={workflow} onChange={setWorkflow} disabled={busy} />
    <Text style={styles.fieldLabel}>提示词</Text><TextInput multiline textAlignVertical="top" value={prompt} onChangeText={setPrompt} placeholder={usesReferences ? "描述你想要的结果，可插入 <Picture N>" : "描述你想生成的图片"} style={[styles.input, styles.promptInput]} />
    {usesReferences && <><View style={styles.rowBetween}><Text style={styles.fieldLabel}>参考图 ({references.length}/{descriptor.maxReferences}){workflow === "qwen_image_2_1_8gb_edit" ? " · 第一张为目标图" : ""}</Text><View style={styles.rowActions}><Pressable disabled={busy} onPress={onPickLibrary} style={[styles.textButton, busy && styles.disabled]}><Text style={styles.textButtonText}>从图库中选择</Text></Pressable><Pressable disabled={busy} onPress={onPick} style={[styles.textButton, busy && styles.disabled]}><Text style={styles.textButtonText}>从手机选择</Text></Pressable></View></View>
      <ReferenceImageStrip items={references} onMove={onMove} onRemove={onRemove} onInsertToken={onInsert} /></>}
    {workflow === "qwen_image_2_1_8gb_edit" && <ImageSettings workflow={workflow} value={editDraft} onChange={(next) => setEditDraft(next as EditImageSettingsDraft)} source={references[0]?.width && references[0]?.height ? { width: references[0].width, height: references[0].height } : undefined} />}
    {workflow === "qwen_image_2_1_8gb_t2i" && <ImageSettings workflow={workflow} value={t2iDraft} onChange={(next) => setT2iDraft(next as T2IImageSettingsDraft)} />}
    {workflow === "minimax_h3" && <VideoSettings value={videoDraft} onChange={setVideoDraft} />}
    {message ? <Text style={message.includes("已进入") ? styles.success : styles.error}>{message}</Text> : null}<PrimaryButton title={busy ? "处理中..." : workflow === "minimax_h3" ? "提交视频任务" : workflow === "qwen_edit_2511" || workflow === "qwen_image_2_1_8gb_edit" ? "提交图片编辑任务" : "提交文生图任务"} onPress={onSubmit} disabled={busy} />
  </View>;
}

function TasksPage({ jobs, onRefresh }: { jobs: GenerationJob[]; onRefresh: () => Promise<void> }) {
  const [now, setNow] = useState(Date.now() / 1000);
  useEffect(() => { const timer = setInterval(() => setNow(Date.now() / 1000), 1000); return () => clearInterval(timer); }, []);
  return <View style={styles.page}><View style={styles.rowBetween}><Text style={styles.pageTitle}>任务</Text><Pressable onPress={onRefresh} style={styles.textButton}><Text style={styles.textButtonText}>刷新</Text></Pressable></View>{jobs.length === 0 ? <Text style={styles.emptyPage}>还没有任务</Text> : jobs.map((job) => { const knownWorkflow = job.workflow && Object.prototype.hasOwnProperty.call(WORKFLOW_DESCRIPTORS, job.workflow) ? WORKFLOW_DESCRIPTORS[job.workflow].label : undefined; return <View key={job.id} style={styles.rowItem}><View style={styles.rowMain}><Text style={styles.rowTitle}>{knownWorkflow || (job.kind === "image" ? "图片编辑" : "参考图生视频")}</Text><Text style={styles.rowSub}>{job.id.slice(-8)} · {job.status}</Text>{job.status === "running" && job.started_at ? <Text style={styles.status}>{formatElapsed(job.started_at, now)}</Text> : null}{job.error ? <Text style={styles.error}>{job.error}</Text> : null}</View><Text style={styles.status}>{job.artifacts.length ? `${job.artifacts.length} 个产物` : ""}</Text></View>; })}</View>;
}

function ArtifactsPage({ artifacts, api, onRefresh }: { artifacts: Artifact[]; api: RemoteApi; onRefresh: () => Promise<void> }) {
  const [selected, setSelected] = useState<Artifact | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  async function saveOrShare(artifact: Artifact, share: boolean) {
    try {
      const url = api.mediaUrl(`/api/v1/artifacts/${encodeURIComponent(artifact.id)}/content`);
      const target = `${FileSystem.cacheDirectory || ""}${artifact.id}${artifact.mime_type.includes("video") ? ".mp4" : ".png"}`;
      const result = await FileSystem.downloadAsync(url, target, { headers: { Authorization: `Bearer ${getToken(api)}` } });
      if (share && await Sharing.isAvailableAsync()) await Sharing.shareAsync(result.uri);
      else { const permission = await MediaLibrary.requestPermissionsAsync(); if (permission.granted) await MediaLibrary.saveToLibraryAsync(result.uri); }
    } catch (cause) { Alert.alert("保存失败", errorText(cause)); }
  }
  async function remove(artifact: Artifact) {
    setDeleting(artifact.id);
    try { await api.deleteArtifact(artifact.id); if (selected?.id === artifact.id) setSelected(null); await onRefresh(); }
    catch (cause) { Alert.alert("删除失败", errorText(cause)); }
    finally { setDeleting(null); }
  }
  const confirmDelete = (artifact: Artifact) => Alert.alert("删除电脑上的产物", "这会永久删除 Gateway 保存的产物文件，无法恢复。电脑图库原图不会删除。", [{ text: "取消", style: "cancel" }, { text: "永久删除", style: "destructive", onPress: () => void remove(artifact) }]);
  return <View style={styles.page}><View style={styles.rowBetween}><Text style={styles.pageTitle}>产物</Text><Pressable onPress={onRefresh} style={styles.textButton}><Text style={styles.textButtonText}>刷新</Text></Pressable></View>{artifacts.length === 0 ? <Text style={styles.emptyPage}>生成完成的产物会显示在这里</Text> : artifacts.map((artifact) => { const url = api.mediaUrl(`/api/v1/artifacts/${encodeURIComponent(artifact.id)}/content`); return <View key={artifact.id} style={styles.artifact}><Pressable accessibilityLabel={artifact.mime_type.startsWith("image/") ? "放大预览图片" : "预览视频"} onPress={() => setSelected(artifact)} style={styles.preview}>{artifact.mime_type.startsWith("image/") ? <Image source={{ uri: url, headers: { Authorization: `Bearer ${getToken(api)}` } }} style={styles.previewImage} /> : <VideoArtifactThumbnail artifact={artifact} api={api} />}</Pressable><Text style={styles.rowSub}>{artifact.mime_type} · {Math.round(artifact.size / 1024)} KB</Text><View style={styles.actions}><Pressable onPress={() => saveOrShare(artifact, false)} style={styles.secondaryButton}><Text>保存</Text></Pressable><Pressable onPress={() => saveOrShare(artifact, true)} style={styles.secondaryButton}><Text>分享</Text></Pressable><Pressable onPress={() => setSelected(artifact)} style={styles.secondaryButton}><Text>预览</Text></Pressable><Pressable disabled={deleting === artifact.id} onPress={() => confirmDelete(artifact)} style={styles.secondaryButton}><Text style={styles.dangerText}>{deleting === artifact.id ? "删除中" : "删除"}</Text></Pressable></View></View>; })}
    <Modal visible={selected !== null} animationType="slide" onRequestClose={() => setSelected(null)}><SafeAreaView style={styles.viewer}><View style={styles.viewerHeader}><Pressable onPress={() => setSelected(null)}><Text style={styles.viewerControl}>关闭</Text></Pressable></View>
      {selected?.mime_type.startsWith("image/") && <ZoomableImage key={selected.id} source={{ uri: api.mediaUrl(`/api/v1/artifacts/${encodeURIComponent(selected.id)}/content`), headers: { Authorization: `Bearer ${getToken(api)}` } }} />}
      {selected?.mime_type.startsWith("video/") && <VideoPreview artifact={selected} api={api} />}
      {selected && !selected.mime_type.startsWith("image/") && !selected.mime_type.startsWith("video/") && <Text style={styles.viewerText}>该文件暂不支持应用内预览，可保存后用其他应用打开。</Text>}
    </SafeAreaView></Modal>
  </View>;
}

function VideoPreview({ artifact, api }: { artifact: Artifact; api: RemoteApi }) {
  const player = useVideoPlayer({ uri: api.mediaUrl(`/api/v1/artifacts/${encodeURIComponent(artifact.id)}/content`), headers: { Authorization: `Bearer ${getToken(api)}` } });
  return <VideoView player={player} nativeControls style={styles.videoPlayer} />;
}

function VideoArtifactThumbnail({ artifact, api }: { artifact: Artifact; api: RemoteApi }) {
  const player = useVideoPlayer({ uri: api.mediaUrl(`/api/v1/artifacts/${encodeURIComponent(artifact.id)}/content`), headers: { Authorization: `Bearer ${getToken(api)}` } }, (instance) => instance.pause());
  return <View style={styles.videoThumbnail}><VideoView player={player} nativeControls={false} contentFit="cover" surfaceType="textureView" style={styles.previewImage} /><View style={styles.playBadge}><Text style={styles.playBadgeText}>▶</Text></View></View>;
}

function LibraryPage({ api, selectionMode, importing, onUse }: { api: RemoteApi; selectionMode: boolean; importing: boolean; onUse: (image: LibraryImage) => Promise<void> }) {
  const [libraries, setLibraries] = useState<Library[]>([]); const [selected, setSelected] = useState<Library | null>(null); const [images, setImages] = useState<LibraryImage[]>([]); const [error, setError] = useState("");
  const [preview, setPreview] = useState<LibraryImage | null>(null);
  const [saving, setSaving] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  useEffect(() => { api.listLibraries().then((result) => { setLibraries(result.libraries); if (result.libraries[0]) setSelected(result.libraries[0]); }).catch((cause) => setError(errorText(cause))); }, [api]);
  useEffect(() => {
    let active = true;
    setImages([]); setHasMore(false);
    if (selected) api.listLibraryImages(selected.id).then((result) => { if (active) { setImages(result.images); setHasMore(result.images.length === 50); } }).catch((cause) => { if (active) setError(errorText(cause)); });
    return () => { active = false; };
  }, [api, selected]);
  async function loadMore() {
    if (!selected || loadingMore || !hasMore) return;
    setLoadingMore(true);
    try {
      const result = await api.listLibraryImages(selected.id, images.length);
      setImages((current) => [...current, ...result.images]);
      setHasMore(result.images.length === 50);
    } catch (cause) { setError(errorText(cause)); }
    finally { setLoadingMore(false); }
  }
  async function saveImage(image: LibraryImage) {
    setSaving(true);
    try {
      const permission = await MediaLibrary.requestPermissionsAsync();
      if (!permission.granted) { Alert.alert("需要相册权限", "请允许应用保存图片到手机相册。"); return; }
      if (!FileSystem.cacheDirectory) throw new Error("无法访问手机缓存目录");
      const extension = image.mime_type === "image/png" ? ".png" : image.mime_type === "image/webp" ? ".webp" : ".jpg";
      const target = `${FileSystem.cacheDirectory}library-${Date.now()}${extension}`;
      const result = await FileSystem.downloadAsync(api.mediaUrl(image.content_url), target, { headers: { Authorization: `Bearer ${getToken(api)}` } });
      if (result.status !== 200) throw new Error(`下载失败（HTTP ${result.status}）`);
      await MediaLibrary.saveToLibraryAsync(result.uri);
      Alert.alert("保存成功", "图片已保存到手机相册。");
    } catch (cause) { Alert.alert("保存失败", errorText(cause)); }
    finally { setSaving(false); }
  }
  return <View style={styles.page}><Text style={styles.pageTitle}>{selectionMode ? "选择电脑参考图" : "电脑图库"}</Text>{selectionMode && <Text style={styles.rowSub}>{importing ? "正在加入参考图..." : "点击图片，将其加入当前生成任务。"}</Text>}{error ? <Text style={styles.error}>{error}</Text> : null}<ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.libraryTabs}>{libraries.map((library) => <Pressable key={library.id} onPress={() => setSelected(library)} style={[styles.libraryTab, selected?.id === library.id && styles.libraryTabActive]}><Text>{library.name}</Text></Pressable>)}</ScrollView>{selected && images.length === 0 ? <Text style={styles.emptyPage}>该目录暂时没有图片</Text> : <View style={styles.imageGrid}>{images.map((image) => <Pressable key={image.id} disabled={selectionMode && importing} accessibilityLabel={selectionMode ? `添加参考图 ${image.name}` : `预览图片 ${image.name}`} onPress={() => selectionMode ? void onUse(image) : setPreview(image)} style={[styles.libraryImage, selectionMode && importing && styles.disabled]}><Image source={{ uri: api.mediaUrl(image.thumbnail_url), headers: { Authorization: `Bearer ${getToken(api)}` } }} style={styles.libraryThumb} /><Text numberOfLines={1} style={styles.imageName}>{image.name}</Text></Pressable>)}</View>}{hasMore && <Pressable disabled={loadingMore} onPress={() => void loadMore()} style={styles.secondaryButton}><Text style={styles.textButtonText}>{loadingMore ? "加载中..." : "加载更多图片"}</Text></Pressable>}
    <Modal visible={preview !== null} animationType="slide" onRequestClose={() => setPreview(null)}><SafeAreaView style={styles.viewer}><View style={styles.viewerHeader}><Pressable onPress={() => setPreview(null)}><Text style={styles.viewerControl}>关闭</Text></Pressable><Pressable disabled={saving} onPress={() => preview && void saveImage(preview)}><Text style={styles.viewerControl}>{saving ? "保存中..." : "保存到手机"}</Text></Pressable></View>{preview && <ZoomableImage key={preview.id} source={{ uri: api.mediaUrl(preview.content_url), headers: { Authorization: `Bearer ${getToken(api)}` } }} />}</SafeAreaView></Modal>
  </View>;
}

function SettingsPage({ pairing, api, onUnpair }: { pairing: PairingDetails; api: RemoteApi; onUnpair: () => Promise<void> }) {
  const [health, setHealth] = useState<Record<string, unknown> | null>(null); const [error, setError] = useState("");
  useEffect(() => { api.health().then(setHealth).catch((cause) => setError(errorText(cause))); }, [api]);
  return <View style={styles.page}><Text style={styles.pageTitle}>设置</Text><Text style={styles.fieldLabel}>连接地址</Text><Text style={styles.mono}>{pairing.baseUrl}</Text><Text style={styles.fieldLabel}>设备</Text><Text style={styles.mono}>{pairing.deviceName}</Text><Text style={styles.fieldLabel}>服务状态</Text><Text style={health?.comfyui && typeof health.comfyui === "object" && "status" in health.comfyui ? styles.success : styles.mono}>{health ? JSON.stringify(health.comfyui) : error || "检查中..."}</Text><Pressable onPress={() => Alert.alert("解除配对", "解除后需要重新输入配对码。", [{ text: "取消" }, { text: "解除", style: "destructive", onPress: onUnpair }])} style={styles.dangerButton}><Text style={styles.dangerText}>解除配对</Text></Pressable></View>;
}

function PrimaryButton({ title, onPress, disabled }: { title: string; onPress: () => void; disabled?: boolean }) { return <Pressable disabled={disabled} onPress={onPress} style={[styles.primaryButton, disabled && styles.disabled]}><Text style={styles.primaryText}>{title}</Text></Pressable>; }
function Centered({ children }: { children: React.ReactNode }) { return <SafeAreaView style={styles.safe}><View style={styles.centerContent}>{children}</View></SafeAreaView>; }
function getToken(api: RemoteApi): string { return api.token || ""; }
function errorText(cause: unknown): string { return cause instanceof Error ? cause.message : "请求失败，请检查 Gateway 状态"; }

const styles = StyleSheet.create({
  viewer: { flex: 1, backgroundColor: "#101827" },
  viewerHeader: { minHeight: 58, paddingHorizontal: 18, flexDirection: "row", alignItems: "center", justifyContent: "space-between" },
  viewerControl: { color: "#fff", fontSize: 18, fontWeight: "700", padding: 8 },
  viewerText: { color: "#fff", fontSize: 15 },
  videoPlayer: { width: "100%", aspectRatio: 16 / 9, marginTop: 60 },
  safe: { flex: 1, backgroundColor: "#f7f8fa" }, centerContent: { flex: 1, justifyContent: "center", padding: 20 }, pairPanel: { backgroundColor: "#fff", borderRadius: 10, padding: 22, borderWidth: 1, borderColor: "#e0e5ec" }, brand: { color: "#14243a", fontSize: 26, fontWeight: "800" }, subtitle: { color: "#64748b", marginTop: 5, marginBottom: 24 }, fieldLabel: { color: "#334155", fontWeight: "700", marginTop: 12, marginBottom: 6 }, input: { minHeight: 44, borderWidth: 1, borderColor: "#cbd5e1", borderRadius: 6, paddingHorizontal: 12, backgroundColor: "#fff", color: "#182333" }, promptInput: { minHeight: 120, paddingTop: 12 }, hint: { color: "#64748b", fontSize: 12, lineHeight: 18, marginTop: 14 }, error: { color: "#b42318", marginTop: 10, lineHeight: 19 }, success: { color: "#19703b", marginTop: 10 }, appShell: { flex: 1 }, header: { paddingHorizontal: 18, paddingTop: 12, paddingBottom: 10, flexDirection: "row", justifyContent: "space-between", alignItems: "center", backgroundColor: "#fff", borderBottomWidth: 1, borderBottomColor: "#e5e7eb" }, headerTitle: { color: "#14243a", fontSize: 18, fontWeight: "800" }, headerSub: { color: "#64748b", fontSize: 11, marginTop: 2 }, statusDot: { width: 10, height: 10, borderRadius: 5, backgroundColor: "#2ca66f" }, content: { padding: 16, paddingBottom: 26 }, page: { gap: 8 }, pageTitle: { color: "#16263d", fontSize: 22, fontWeight: "800", marginBottom: 4 }, segment: { flexDirection: "row", padding: 3, borderRadius: 7, backgroundColor: "#e8ecf2", marginBottom: 8 }, segmentItem: { flex: 1, alignItems: "center", paddingVertical: 10, borderRadius: 5 }, segmentSelected: { backgroundColor: "#fff" }, segmentText: { color: "#64748b", fontWeight: "700" }, segmentTextSelected: { color: "#1769aa", fontWeight: "800" }, rowBetween: { flexDirection: "row", alignItems: "center", justifyContent: "space-between" }, rowActions: { flexDirection: "row", alignItems: "center" }, textButton: { padding: 8 }, textButtonText: { color: "#1769aa", fontWeight: "700" }, primaryButton: { minHeight: 46, borderRadius: 6, backgroundColor: "#1769aa", alignItems: "center", justifyContent: "center", marginTop: 18 }, primaryText: { color: "#fff", fontWeight: "800" }, disabled: { opacity: 0.55 }, tabBar: { minHeight: 62, flexDirection: "row", backgroundColor: "#fff", borderTopWidth: 1, borderTopColor: "#e5e7eb" }, tab: { flex: 1, justifyContent: "center", alignItems: "center", borderTopWidth: 2, borderTopColor: "transparent" }, tabActive: { borderTopColor: "#1769aa" }, tabText: { color: "#64748b", fontSize: 12 }, tabTextActive: { color: "#1769aa", fontWeight: "800" }, emptyPage: { color: "#64748b", textAlign: "center", paddingVertical: 40 }, rowItem: { flexDirection: "row", justifyContent: "space-between", alignItems: "center", paddingVertical: 14, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#d8dde5" }, rowMain: { flex: 1 }, rowTitle: { color: "#1e293b", fontWeight: "700" }, rowSub: { color: "#64748b", fontSize: 12, marginTop: 4 }, status: { color: "#1769aa", fontSize: 12 }, artifact: { paddingVertical: 12, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#d8dde5" }, preview: { height: 170, backgroundColor: "#e8ecf2", borderRadius: 7, alignItems: "center", justifyContent: "center", overflow: "hidden" }, previewImage: { width: "100%", height: "100%", resizeMode: "contain" }, videoThumbnail: { width: "100%", height: "100%" }, playBadge: { position: "absolute", left: "50%", top: "50%", width: 46, height: 46, marginLeft: -23, marginTop: -23, borderRadius: 23, backgroundColor: "rgba(15,23,42,0.72)", alignItems: "center", justifyContent: "center" }, playBadgeText: { color: "#fff", fontSize: 20, marginLeft: 3 }, actions: { flexDirection: "row", gap: 7, marginTop: 8 }, secondaryButton: { minHeight: 34, paddingHorizontal: 10, borderRadius: 5, backgroundColor: "#eef2f7", justifyContent: "center" }, libraryTabs: { gap: 7, paddingVertical: 5 }, libraryTab: { borderRadius: 5, backgroundColor: "#e8ecf2", paddingHorizontal: 12, paddingVertical: 9 }, libraryTabActive: { backgroundColor: "#d5eafb" }, imageGrid: { flexDirection: "row", flexWrap: "wrap", gap: 9, marginTop: 8 }, libraryImage: { width: "31.5%", gap: 3 }, libraryThumb: { width: "100%", aspectRatio: 1, borderRadius: 5, backgroundColor: "#e8ecf2" }, imageName: { color: "#475569", fontSize: 11 }, mono: { color: "#475569", fontSize: 12, paddingVertical: 5 }, dangerButton: { minHeight: 44, borderRadius: 6, borderWidth: 1, borderColor: "#d92d20", alignItems: "center", justifyContent: "center", marginTop: 26 }, dangerText: { color: "#b42318", fontWeight: "700" },
});

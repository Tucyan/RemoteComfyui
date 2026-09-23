import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import {
  calculateEditDimensions,
  calculateImageDimensions,
  lockEditDimensions,
  normalizeImageDimensions,
  QWEN_EDIT_SCALE,
  VIDEO_RATIOS,
  type WorkflowId,
} from "../domain/draft";

export type EditImageSettingsDraft = { editSizeMode: "scale" | "dimensions"; sizeAnchor: "width" | "height"; scaleFactor: number; width: string; height: string };
export type T2IImageSettingsDraft = { ratio: string; quality: number; custom: boolean; width: string; height: string };

type Props = {
  workflow: Extract<WorkflowId, "qwen_image_2_1_8gb_edit" | "qwen_image_2_1_8gb_t2i">;
  value: EditImageSettingsDraft | T2IImageSettingsDraft;
  onChange: (next: EditImageSettingsDraft | T2IImageSettingsDraft) => void;
  source?: { width: number; height: number };
};

export function ImageSettings({ workflow, value, onChange, source }: Props) {
  const [trackWidth, setTrackWidth] = useState(1);
  if (workflow === "qwen_image_2_1_8gb_edit") {
    const edit = value as EditImageSettingsDraft;
    const calculated = source && edit.editSizeMode === "dimensions" && edit.sizeAnchor && Number(edit[edit.sizeAnchor]) > 0
      ? safe(() => lockEditDimensions(source.width, source.height, edit.sizeAnchor, Number(edit[edit.sizeAnchor])))
      : source ? safe(() => calculateEditDimensions(source.width, source.height, edit.scaleFactor)) : undefined;
    const current = calculated ?? (!source ? safe(() => ({ width: Number(edit.width), height: Number(edit.height), adjusted: false })) : undefined);
    const setScale = (position: number) => {
      const scaleFactor = Math.round((QWEN_EDIT_SCALE.min + (QWEN_EDIT_SCALE.max - QWEN_EDIT_SCALE.min) * Math.min(1, Math.max(0, position / trackWidth))) * 10) / 10;
      const dimensions = source ? safe(() => calculateEditDimensions(source.width, source.height, scaleFactor)) : undefined;
      onChange({ ...edit, editSizeMode: "scale", scaleFactor, ...(dimensions ? { width: String(dimensions.width), height: String(dimensions.height) } : {}) });
    };
    const setDimension = (field: "width" | "height", raw: string) => {
      if (!/^\d+$/.test(raw) || !source) {
        onChange({ ...edit, editSizeMode: "dimensions", sizeAnchor: field, [field]: raw });
        return;
      }
      const dimensions = safe(() => lockEditDimensions(source.width, source.height, field, Number(raw)));
      const other = field === "width" ? "height" : "width";
      onChange(dimensions
        ? { ...edit, editSizeMode: "dimensions", sizeAnchor: field, [field]: raw, [other]: String(dimensions[other]) }
        : { ...edit, editSizeMode: "dimensions", sizeAnchor: field, [field]: raw });
    };
    return <View style={styles.container}>
      <Text style={styles.label}>相对原图倍率</Text>
      <View style={styles.heading}><Text style={styles.sub}>0.5×</Text><Text style={styles.emphasis}>{edit.scaleFactor.toFixed(1)}×</Text><Text style={styles.sub}>2.0×</Text></View>
      <View style={styles.sliderRow}><Text style={styles.sub}>0.5</Text><View accessibilityRole="adjustable" accessibilityLabel="相对原图倍率" accessibilityValue={{ min: QWEN_EDIT_SCALE.min, max: QWEN_EDIT_SCALE.max, now: edit.scaleFactor, text: `${edit.scaleFactor.toFixed(1)} 倍` }} accessibilityActions={[{ name: "increment" }, { name: "decrement" }]} onAccessibilityAction={(event) => setScale(((edit.scaleFactor + (event.nativeEvent.actionName === "increment" ? QWEN_EDIT_SCALE.step : -QWEN_EDIT_SCALE.step) - QWEN_EDIT_SCALE.min) / (QWEN_EDIT_SCALE.max - QWEN_EDIT_SCALE.min)) * trackWidth)} style={styles.trackTouch} onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)} onStartShouldSetResponder={() => true} onMoveShouldSetResponder={() => true} onResponderGrant={(event) => setScale(event.nativeEvent.locationX)} onResponderMove={(event) => setScale(event.nativeEvent.locationX)}>
        <View style={styles.track}><View style={[styles.trackFill, { width: `${(edit.scaleFactor - QWEN_EDIT_SCALE.min) / (QWEN_EDIT_SCALE.max - QWEN_EDIT_SCALE.min) * 100}%` }]} /><View style={[styles.thumb, { left: `${(edit.scaleFactor - QWEN_EDIT_SCALE.min) / (QWEN_EDIT_SCALE.max - QWEN_EDIT_SCALE.min) * 100}%` }]} /></View>
      </View><Text style={styles.sub}>2.0</Text></View>
      {source ? <Text style={styles.sub}>原图：{source.width} × {source.height}。倍率步进 0.1×。</Text> : <Text style={styles.warning}>先添加目标图片，再设置编辑尺寸。</Text>}
      <View style={styles.dimensionRow}><View style={styles.dimensionField}><Text style={styles.sub}>宽度</Text><TextInput accessibilityLabel="编辑宽度" keyboardType="number-pad" value={edit.width} onChangeText={(width) => setDimension("width", width)} style={styles.input} placeholder={current ? String(current.width) : "宽度"} /></View><View style={styles.dimensionField}><Text style={styles.sub}>高度</Text><TextInput accessibilityLabel="编辑高度" keyboardType="number-pad" value={edit.height} onChangeText={(height) => setDimension("height", height)} style={styles.input} placeholder={current ? String(current.height) : "高度"} /></View></View>
      {current ? <Text style={styles.sub}>实际提交尺寸：{current.width} × {current.height}（32 的倍数，最长边不超过 2048）</Text> : <Text style={styles.warning}>当前尺寸超出 2048 像素边长限制，请降低倍率或调整尺寸。</Text>}
    </View>;
  }

  const t2i = value as T2IImageSettingsDraft;
  const calculated = safe(() => calculateImageDimensions(t2i.ratio, t2i.quality));
  const requestedWidth = t2i.custom ? Number(t2i.width) : calculated?.width;
  const requestedHeight = t2i.custom ? Number(t2i.height) : calculated?.height;
  const normalized = requestedWidth && requestedHeight ? safe(() => normalizeImageDimensions(requestedWidth, requestedHeight)) : undefined;
  const set = (patch: Partial<T2IImageSettingsDraft>) => onChange({ ...t2i, ...patch });
  const slide = (position: number) => set({ quality: Math.round((0.2 + 1.3 * Math.min(1, Math.max(0, position / trackWidth))) * 10) / 10 });
  return <View style={styles.container}>
    <Text style={styles.label}>图片比例</Text>
    <View style={styles.ratios}>{Object.entries(VIDEO_RATIOS).map(([ratio, [w, h]]) => <Pressable key={ratio} accessibilityRole="radio" accessibilityState={{ selected: t2i.ratio === ratio }} onPress={() => set({ ratio })} style={[styles.ratioButton, t2i.ratio === ratio && styles.selected]}>
      <View style={[styles.rectangle, { width: 32 * w / Math.max(w, h), height: 32 * h / Math.max(w, h) }]} /><Text style={styles.ratioText}>{ratio}</Text>
    </Pressable>)}</View>
    <View style={styles.heading}><Text style={styles.label}>目标清晰度</Text><Text style={styles.sub}>{t2i.quality.toFixed(1)} MP</Text></View>
    <View style={styles.sliderRow}><Text style={styles.sub}>0.2</Text><View accessibilityRole="adjustable" accessibilityLabel="文生图目标清晰度" accessibilityValue={{ min: 0.2, max: 1.5, now: t2i.quality, text: `${t2i.quality.toFixed(1)} MP` }} accessibilityActions={[{ name: "increment" }, { name: "decrement" }]} onAccessibilityAction={(event) => slide(((t2i.quality + (event.nativeEvent.actionName === "increment" ? 0.1 : -0.1) - 0.2) / 1.3) * trackWidth)} style={styles.trackTouch} onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)} onStartShouldSetResponder={() => true} onMoveShouldSetResponder={() => true} onResponderGrant={(event) => slide(event.nativeEvent.locationX)} onResponderMove={(event) => slide(event.nativeEvent.locationX)}><View style={styles.track}><View style={[styles.trackFill, { width: `${(t2i.quality - 0.2) / 1.3 * 100}%` }]} /><View style={[styles.thumb, { left: `${(t2i.quality - 0.2) / 1.3 * 100}%` }]} /></View></View><Text style={styles.sub}>1.5</Text></View>
    <Text style={styles.sub}>当前约 {calculated ? (calculated.width * calculated.height / 1_000_000).toFixed(2) : "—"} MP，{calculated ? `${calculated.width} × ${calculated.height}` : "比例或清晰度无效"}。</Text>
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: t2i.custom }} onPress={() => set({ custom: !t2i.custom })} style={styles.checkRow}><Text style={styles.checkbox}>{t2i.custom ? "☑" : "□"}</Text><Text>自定义尺寸</Text></Pressable>
    {t2i.custom && <View style={styles.dimensionRow}><View style={styles.dimensionField}><Text style={styles.sub}>宽度</Text><TextInput accessibilityLabel="文生图宽度" keyboardType="number-pad" value={t2i.width} onChangeText={(width) => set({ width })} style={styles.input} placeholder="宽度" /></View><View style={styles.dimensionField}><Text style={styles.sub}>高度</Text><TextInput accessibilityLabel="文生图高度" keyboardType="number-pad" value={t2i.height} onChangeText={(height) => set({ height })} style={styles.input} placeholder="高度" /></View></View>}
    {normalized ? <Text style={normalized.adjusted ? styles.warning : styles.sub}>实际提交尺寸：{normalized.width} × {normalized.height}{normalized.adjusted ? "（自动对齐到最近的 8 倍数）" : "（宽高是 8 的倍数）"}，最长边不超过 2048。</Text> : <Text style={styles.warning}>请填写 1～2048 之间的有效尺寸。</Text>}
  </View>;
}

function safe<T>(fn: () => T): T | undefined {
  try { return fn(); } catch { return undefined; }
}

const styles = StyleSheet.create({
  container: { gap: 9, paddingTop: 8 }, label: { color: "#334155", fontWeight: "700", marginTop: 4 }, sub: { color: "#64748b", fontSize: 12 }, warning: { color: "#9a6700", fontSize: 12, lineHeight: 18 }, emphasis: { color: "#1769aa", fontWeight: "700" }, ratios: { flexDirection: "row", flexWrap: "wrap", gap: 6 }, ratioButton: { width: "23%", minHeight: 72, backgroundColor: "#fff", borderWidth: 1, borderColor: "#d8dde5", borderRadius: 7, alignItems: "center", justifyContent: "center", gap: 5 }, selected: { backgroundColor: "#e6f2fb", borderColor: "#1769aa" }, rectangle: { borderWidth: 2, borderColor: "#1769aa", borderRadius: 2 }, ratioText: { color: "#1e293b", fontSize: 12, fontWeight: "600" }, heading: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" }, sliderRow: { flexDirection: "row", alignItems: "center", gap: 8 }, trackTouch: { flex: 1, height: 40, justifyContent: "center" }, track: { height: 6, backgroundColor: "#cbd5e1", borderRadius: 3 }, trackFill: { height: 6, backgroundColor: "#1769aa", borderRadius: 3 }, thumb: { position: "absolute", top: -7, width: 20, height: 20, marginLeft: -10, borderRadius: 10, backgroundColor: "#1769aa" }, dimensionRow: { flexDirection: "row", gap: 8 }, dimensionField: { flex: 1, gap: 5 }, input: { height: 42, borderWidth: 1, borderColor: "#cbd5e1", borderRadius: 6, backgroundColor: "#fff", color: "#1e293b", paddingHorizontal: 10 }, checkRow: { flexDirection: "row", alignItems: "center", gap: 7, paddingVertical: 5 }, checkbox: { color: "#1769aa", fontSize: 22 },
});

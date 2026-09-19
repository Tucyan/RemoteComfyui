import { useState } from "react";
import { Pressable, StyleSheet, Text, TextInput, View } from "react-native";
import { adjustVideoFrames, calculateVideoDimensions, VIDEO_RATIOS } from "../domain/draft";

export type VideoDraft = { ratio: string; quality: number; custom: boolean; width: string; height: string; frames: string };
type Props = { value: VideoDraft; onChange: (next: VideoDraft) => void };

export function VideoSettings({ value, onChange }: Props) {
  const [trackWidth, setTrackWidth] = useState(1);
  const calculated = calculateVideoDimensions(value.ratio, value.quality);
  const width = value.custom ? Number(value.width) || calculated.width : calculated.width;
  const height = value.custom ? Number(value.height) || calculated.height : calculated.height;
  const set = (patch: Partial<VideoDraft>) => onChange({ ...value, ...patch });
  const slide = (position: number) => set({ quality: Math.round((0.2 + 1.3 * Math.min(1, Math.max(0, position / trackWidth))) * 10) / 10 });

  return <View style={styles.container}>
    <Text style={styles.label}>视频比例</Text>
    <View style={styles.ratios}>{Object.entries(VIDEO_RATIOS).map(([ratio, [w, h]]) => <Pressable key={ratio} onPress={() => set({ ratio })} style={[styles.ratioButton, value.ratio === ratio && styles.selected]}>
      <View style={[styles.rectangle, { width: 36 * w / Math.max(w, h), height: 36 * h / Math.max(w, h) }]} />
      <Text style={styles.ratioText}>{ratio}</Text>
    </Pressable>)}</View>
    <View style={styles.heading}><Text style={styles.label}>清晰度</Text><Text style={styles.sub}>{value.quality.toFixed(1)} MP</Text></View>
    <View style={styles.sliderRow}><Text style={styles.sub}>0.2</Text><View style={styles.trackTouch} onLayout={(event) => setTrackWidth(event.nativeEvent.layout.width)} onStartShouldSetResponder={() => true} onMoveShouldSetResponder={() => true} onResponderGrant={(event) => slide(event.nativeEvent.locationX)} onResponderMove={(event) => slide(event.nativeEvent.locationX)}>
      <View style={styles.track}><View style={[styles.trackFill, { width: `${(value.quality - 0.2) / 1.3 * 100}%` }]} /><View style={[styles.thumb, { left: `${(value.quality - 0.2) / 1.3 * 100}%` }]} /></View>
    </View><Text style={styles.sub}>1.5</Text></View>
    <Text style={styles.sub}>目标总百万像素；当前约 {(calculated.width * calculated.height / 1_000_000).toFixed(2)} MP，{calculated.width} × {calculated.height}。部分竖屏比例受高度上限约束。</Text>
    <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: value.custom }} onPress={() => set({ custom: !value.custom })} style={styles.checkRow}><Text style={styles.checkbox}>{value.custom ? "☑" : "□"}</Text><Text>自定义尺寸</Text></Pressable>
    {value.custom && <View style={styles.dimensionRow}><View style={styles.dimensionField}><Text style={styles.sub}>宽度</Text><TextInput keyboardType="number-pad" value={value.width} onChangeText={(widthText) => set({ width: widthText })} style={styles.input} placeholder="宽度" /></View><View style={styles.dimensionField}><Text style={styles.sub}>高度</Text><TextInput keyboardType="number-pad" value={value.height} onChangeText={(heightText) => set({ height: heightText })} style={styles.input} placeholder="高度" /></View></View>}
    <Text style={styles.sub}>实际生成尺寸：{width} × {height}（宽高须是 32 的倍数）</Text>
    <Text style={styles.label}>生成帧数</Text>
    <View style={styles.frameRow}><Pressable accessibilityLabel="减少帧数" onPress={() => set({ frames: String(adjustVideoFrames(Number(value.frames), -1)) })} style={styles.step}><Text style={styles.stepText}>−</Text></Pressable><TextInput accessibilityLabel="生成帧数" keyboardType="number-pad" value={value.frames} onChangeText={(frames) => set({ frames })} style={[styles.input, styles.frameInput]} /><Pressable accessibilityLabel="增加帧数" onPress={() => set({ frames: String(adjustVideoFrames(Number(value.frames), 1)) })} style={styles.step}><Text style={styles.stepText}>＋</Text></Pressable></View>
    <Text style={styles.sub}>范围 5–362，满足 17n+5（例如 5、22、39）</Text>
  </View>;
}

const styles = StyleSheet.create({
  container: { gap: 9, paddingTop: 8 }, label: { color: "#334155", fontWeight: "700", marginTop: 4 }, sub: { color: "#64748b", fontSize: 12 }, ratios: { flexDirection: "row", flexWrap: "wrap", gap: 6 }, ratioButton: { width: "23%", minHeight: 76, backgroundColor: "#fff", borderWidth: 1, borderColor: "#d8dde5", borderRadius: 7, alignItems: "center", justifyContent: "center", gap: 5 }, selected: { backgroundColor: "#e6f2fb", borderColor: "#1769aa" }, rectangle: { borderWidth: 2, borderColor: "#1769aa", borderRadius: 2 }, ratioText: { color: "#1e293b", fontSize: 12, fontWeight: "600" }, heading: { flexDirection: "row", justifyContent: "space-between" }, sliderRow: { flexDirection: "row", alignItems: "center", gap: 8 }, trackTouch: { flex: 1, height: 36, justifyContent: "center" }, track: { height: 6, backgroundColor: "#cbd5e1", borderRadius: 3 }, trackFill: { height: 6, backgroundColor: "#1769aa", borderRadius: 3 }, thumb: { position: "absolute", top: -7, width: 20, height: 20, marginLeft: -10, borderRadius: 10, backgroundColor: "#1769aa" }, checkRow: { flexDirection: "row", alignItems: "center", gap: 7, paddingVertical: 5 }, checkbox: { color: "#1769aa", fontSize: 22 }, dimensionRow: { flexDirection: "row", gap: 8 }, dimensionField: { flex: 1, gap: 5 }, input: { height: 42, borderWidth: 1, borderColor: "#cbd5e1", borderRadius: 6, backgroundColor: "#fff", color: "#1e293b", paddingHorizontal: 10 }, frameRow: { flexDirection: "row", gap: 8 }, frameInput: { flex: 1, textAlign: "center" }, step: { width: 48, borderRadius: 6, backgroundColor: "#e6f2fb", alignItems: "center", justifyContent: "center" }, stepText: { fontSize: 22, color: "#1769aa", fontWeight: "700" },
});

import { Pressable, StyleSheet, Text, View } from "react-native";
import { VIDEO_FRAMES, VIDEO_PRESETS } from "../domain/draft";

type Props = { preset: string; frames: number; onPreset: (value: string) => void; onFrames: (value: number) => void };

export function VideoSettings({ preset, frames, onPreset, onFrames }: Props) {
  return (
    <View style={styles.container}>
      <Text style={styles.label}>分辨率</Text>
      <View style={styles.options}>
        {Object.entries(VIDEO_PRESETS).map(([key, option]) => (
          <Pressable key={key} onPress={() => onPreset(key)} style={[styles.option, preset === key && styles.selected]}>
            <Text style={[styles.optionText, preset === key && styles.selectedText]}>{option.label}</Text>
            <Text style={styles.dimensions}>{option.width} × {option.height}</Text>
          </Pressable>
        ))}
      </View>
      <Text style={styles.label}>生成帧数</Text>
      <View style={styles.options}>
        {VIDEO_FRAMES.map((value) => (
          <Pressable key={value} onPress={() => onFrames(value)} style={[styles.frame, frames === value && styles.selected]}>
            <Text style={[styles.optionText, frames === value && styles.selectedText]}>{value} 帧</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { gap: 8, paddingTop: 8 },
  label: { color: "#334155", fontWeight: "700", marginTop: 4 },
  options: { flexDirection: "row", flexWrap: "wrap", gap: 6 },
  option: { minWidth: "30%", flexGrow: 1, borderWidth: 1, borderColor: "#d8dde5", borderRadius: 6, padding: 8, backgroundColor: "#fff" },
  frame: { borderWidth: 1, borderColor: "#d8dde5", borderRadius: 6, paddingVertical: 9, paddingHorizontal: 10, backgroundColor: "#fff" },
  selected: { borderColor: "#1769aa", backgroundColor: "#e6f2fb" },
  optionText: { color: "#1e293b", fontWeight: "600", fontSize: 12 },
  selectedText: { color: "#0f568f" },
  dimensions: { color: "#64748b", fontSize: 11, marginTop: 2 },
});

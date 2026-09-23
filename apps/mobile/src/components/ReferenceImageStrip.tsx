import { Image, Pressable, StyleSheet, Text, View } from "react-native";

export type ReferenceItem = { id: string; name: string; uri?: string; width?: number; height?: number };

type Props = {
  items: ReferenceItem[];
  onMove: (from: number, to: number) => void;
  onRemove: (index: number) => void;
  onInsertToken: (index: number) => void;
};

export function ReferenceImageStrip({ items, onMove, onRemove, onInsertToken }: Props) {
  return (
    <View style={styles.list}>
      {items.map((item, index) => (
        <View key={item.id} style={styles.item}>
          {item.uri ? <Image source={{ uri: item.uri }} style={styles.thumb} /> : <View style={[styles.thumb, styles.placeholder]}><Text>图</Text></View>}
          <View style={styles.meta}>
            <Text style={styles.number}>Picture {index + 1}</Text>
            <Text numberOfLines={1} style={styles.name}>{item.name}</Text>
            <View style={styles.actions}>
              <Pressable accessibilityLabel={`move reference ${index + 1} up`} disabled={index === 0} onPress={() => onMove(index, index - 1)} style={styles.smallButton}><Text>↑</Text></Pressable>
              <Pressable accessibilityLabel={`move reference ${index + 1} down`} disabled={index === items.length - 1} onPress={() => onMove(index, index + 1)} style={styles.smallButton}><Text>↓</Text></Pressable>
              <Pressable accessibilityLabel={`insert picture ${index + 1}`} onPress={() => onInsertToken(index + 1)} style={styles.smallButton}><Text>&lt;N&gt;</Text></Pressable>
              <Pressable accessibilityLabel={`remove reference ${index + 1}`} onPress={() => onRemove(index)} style={[styles.smallButton, styles.remove]}><Text>删</Text></Pressable>
            </View>
          </View>
        </View>
      ))}
      {items.length === 0 && <Text style={styles.empty}>至少添加一张参考图</Text>}
    </View>
  );
}

const styles = StyleSheet.create({
  list: { gap: 8 },
  item: { flexDirection: "row", borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: "#d8dde5", paddingVertical: 8, gap: 10 },
  thumb: { width: 72, height: 72, borderRadius: 6, backgroundColor: "#e8ecf2" },
  placeholder: { alignItems: "center", justifyContent: "center" },
  meta: { flex: 1, justifyContent: "space-between", minWidth: 0 },
  number: { color: "#1b2a41", fontWeight: "700" },
  name: { color: "#64748b", fontSize: 12 },
  actions: { flexDirection: "row", gap: 6 },
  smallButton: { minWidth: 34, minHeight: 32, alignItems: "center", justifyContent: "center", borderRadius: 5, backgroundColor: "#eef2f7", paddingHorizontal: 7 },
  remove: { backgroundColor: "#fee2e2" },
  empty: { color: "#64748b", paddingVertical: 12 },
});

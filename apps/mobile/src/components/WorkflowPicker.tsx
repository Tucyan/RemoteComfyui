import { Pressable, StyleSheet, Text, View } from "react-native";
import { WORKFLOW_DESCRIPTORS, type WorkflowId } from "../domain/draft";

type Props = { value: WorkflowId; onChange: (workflow: WorkflowId) => void; disabled?: boolean };

export function WorkflowPicker({ value, onChange, disabled = false }: Props) {
  return <View style={styles.grid}>
    {(Object.entries(WORKFLOW_DESCRIPTORS) as Array<[WorkflowId, typeof WORKFLOW_DESCRIPTORS[WorkflowId]]>).map(([id, workflow]) => {
      const selected = value === id;
      return <Pressable
        key={id}
        accessibilityRole="radio"
        accessibilityState={{ selected }}
        disabled={disabled}
        onPress={() => onChange(id)}
        style={[styles.card, selected && styles.selected, disabled && styles.disabled]}
      >
        <Text style={[styles.title, selected && styles.selectedText]}>{workflow.label}</Text>
        <Text style={styles.description}>{workflow.description}</Text>
      </Pressable>;
    })}
  </View>;
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  card: { width: "48%", minHeight: 76, padding: 10, borderRadius: 8, borderWidth: 1, borderColor: "#cbd5e1", backgroundColor: "#fff", justifyContent: "center", gap: 4 },
  selected: { borderColor: "#1769aa", backgroundColor: "#e6f2fb" },
  title: { color: "#1e293b", fontWeight: "700", fontSize: 13 },
  selectedText: { color: "#145b91" },
  disabled: { opacity: 0.65 },
  description: { color: "#64748b", fontSize: 11, lineHeight: 15 },
});

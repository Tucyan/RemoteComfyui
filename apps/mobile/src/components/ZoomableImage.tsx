import { useMemo, useRef, useState } from "react";
import { Image, type ImageSourcePropType, PanResponder, StyleSheet, Text, View } from "react-native";
import { clampZoom, touchDistance } from "../domain/zoom";

export function ZoomableImage({ source }: { source: ImageSourcePropType }) {
  const [scale, setScale] = useState(1);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const scaleRef = useRef(1);
  const offsetRef = useRef({ x: 0, y: 0 });
  const sizeRef = useRef({ width: 0, height: 0 });
  const pinchRef = useRef<{ distance: number; scale: number } | null>(null);
  const dragRef = useRef<{ x: number; y: number; offsetX: number; offsetY: number } | null>(null);

  const responder = useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => true,
    onMoveShouldSetPanResponder: () => true,
    onPanResponderMove: (event) => {
      const touches = event.nativeEvent.touches;
      const distance = touchDistance(touches);
      if (distance !== null && distance > 0) {
        dragRef.current = null;
        if (!pinchRef.current) pinchRef.current = { distance, scale: scaleRef.current };
        const next = clampZoom(pinchRef.current.scale * distance / pinchRef.current.distance);
        scaleRef.current = next;
        setScale(next);
        const limitX = sizeRef.current.width * (next - 1) / 2;
        const limitY = sizeRef.current.height * (next - 1) / 2;
        const nextOffset = {
          x: Math.max(-limitX, Math.min(limitX, offsetRef.current.x)),
          y: Math.max(-limitY, Math.min(limitY, offsetRef.current.y)),
        };
        offsetRef.current = nextOffset;
        setOffset(nextOffset);
        return;
      }
      pinchRef.current = null;
      if (touches.length !== 1 || scaleRef.current <= 1) { dragRef.current = null; return; }
      const point = touches[0];
      if (!dragRef.current) dragRef.current = { x: point.pageX, y: point.pageY, offsetX: offsetRef.current.x, offsetY: offsetRef.current.y };
      const limitX = sizeRef.current.width * (scaleRef.current - 1) / 2;
      const limitY = sizeRef.current.height * (scaleRef.current - 1) / 2;
      const next = {
        x: Math.max(-limitX, Math.min(limitX, dragRef.current.offsetX + point.pageX - dragRef.current.x)),
        y: Math.max(-limitY, Math.min(limitY, dragRef.current.offsetY + point.pageY - dragRef.current.y)),
      };
      offsetRef.current = next;
      setOffset(next);
    },
    onPanResponderRelease: () => { pinchRef.current = null; dragRef.current = null; },
    onPanResponderTerminate: () => { pinchRef.current = null; dragRef.current = null; },
    onPanResponderTerminationRequest: () => false,
  }), []);

  return <View style={styles.container} onLayout={(event) => { sizeRef.current = event.nativeEvent.layout; }} {...responder.panHandlers}>
    <Image source={source} resizeMode="contain" style={[styles.image, { transform: [{ translateX: offset.x }, { translateY: offset.y }, { scale }] }]} />
    <Text style={styles.hint}>双指缩放 · 单指拖动 · {scale.toFixed(1)}×</Text>
  </View>;
}

const styles = StyleSheet.create({
  container: { flex: 1, overflow: "hidden", justifyContent: "center" },
  image: { width: "100%", height: "100%" },
  hint: { position: "absolute", bottom: 12, alignSelf: "center", color: "#fff", backgroundColor: "#0009", paddingHorizontal: 10, paddingVertical: 5, borderRadius: 5, fontSize: 12 },
});

# 参考图缩略图与预览 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成页中的手机和电脑参考图都显示缩略图，点击缩略图后能查看原图，并通过双指缩放、单指拖动检查细节。

**Architecture:** 每张参考图保留缩略图与预览图两个 React Native `Image` source。手机选图使用本地 URI；电脑图库导入使用列表返回的缩略图和原图 URL，并为两个 source 附加配对令牌。参考图列表内用 `Modal` 和现有 `ZoomableImage` 显示预览。

**Tech Stack:** Expo 54、React Native 0.81、TypeScript、Vitest。

---

## 文件职责

- 新建 `apps/mobile/src/domain/referenceImages.ts`：从手机 URI 或电脑图库条目构造缩略图与预览图 source。
- 新建 `apps/mobile/tests/referenceImages.test.ts`：验证电脑图片两种 URL、鉴权头与手机本地 URI。
- 修改 `apps/mobile/src/components/ReferenceImageStrip.tsx`：显示缩略图，点击后弹出可缩放、可拖动的预览。
- 修改 `apps/mobile/App.tsx`：选图和导入时保存两个 source，传给参考图列表。
- 更新项目根目录的 `task_plan.md`、`findings.md`、`progress.md`：记录实施和验证结果。

## Task 1：参考图来源

**Files:**

- Create: `apps/mobile/tests/referenceImages.test.ts`
- Create: `apps/mobile/src/domain/referenceImages.ts`

- [x] **Step 1：写失败测试。** 测试手机图片的两个 source 都指向本地 URI；电脑图库图片的缩略图使用 `thumbnail_url`，预览使用 `content_url`，两者都带 `Bearer` 令牌。示例测试核心断言：

```ts
const api = new RemoteApi("http://gateway:3000", "rc_test");
const sources = libraryReferenceSources(api, {
  id: "libimg_1", name: "desk.png", relative_path: "desk.png",
  mime_type: "image/png", size: 5, mtime: 1,
  thumbnail_url: "/api/v1/library-images/libimg_1/thumbnail",
  content_url: "/api/v1/library-images/libimg_1/content",
});
expect(sources.thumbnailSource).toEqual({
  uri: "http://gateway:3000/api/v1/library-images/libimg_1/thumbnail",
  headers: { Authorization: "Bearer rc_test" },
});
expect(sources.previewSource).toEqual({
  uri: "http://gateway:3000/api/v1/library-images/libimg_1/content",
  headers: { Authorization: "Bearer rc_test" },
});
expect(phoneReferenceSources("file:///picked/photo.jpg")).toEqual({
  thumbnailSource: { uri: "file:///picked/photo.jpg" },
  previewSource: { uri: "file:///picked/photo.jpg" },
});
```

- [x] **Step 2：确认测试因缺少函数而失败。** 在 `apps/mobile` 执行 `npm test -- tests/referenceImages.test.ts`，预期为导出不存在导致的失败。
- [x] **Step 3：实现最小来源构造。** 在 `referenceImages.ts` 写入：

```ts
import type { ImageSourcePropType } from "react-native";
import type { LibraryImage, RemoteApi } from "../api/client";

export type ReferenceSources = {
  thumbnailSource: ImageSourcePropType;
  previewSource: ImageSourcePropType;
};

export function phoneReferenceSources(uri: string): ReferenceSources {
  return {
    thumbnailSource: { uri },
    previewSource: { uri },
  };
}

export function libraryReferenceSources(api: RemoteApi, image: LibraryImage): ReferenceSources {
  const headers = { Authorization: `Bearer ${api.token}` };
  return {
    thumbnailSource: { uri: api.mediaUrl(image.thumbnail_url), headers },
    previewSource: { uri: api.mediaUrl(image.content_url), headers },
  };
}
```
- [x] **Step 4：复跑相同测试。** 预期所有新测试通过。

## Task 2：生成页缩略图及预览

**Files:**

- Modify: `apps/mobile/src/components/ReferenceImageStrip.tsx`
- Modify: `apps/mobile/App.tsx`

- [x] **Step 1：调整 `ReferenceItem`。** 将 `ReferenceImageStrip.tsx` 的类型改为以下字段，移除原有可选 `uri`：

```ts
import type { ImageSourcePropType } from "react-native";

export type ReferenceItem = {
  id: string;
  name: string;
  thumbnailSource: ImageSourcePropType;
  previewSource: ImageSourcePropType;
  width?: number;
  height?: number;
};
```

- [x] **Step 2：接入手机选图。** 在 `App.tsx` 导入 `phoneReferenceSources`。上传成功后，替换 `pickReferences` 中构造 `next` 的语句：

```ts
const next = uploaded.assets.map((asset, index) => ({
  id: asset.id,
  assetId: asset.id,
  name: asset.filename,
  ...phoneReferenceSources(result.assets[index].uri),
  width: asset.width,
  height: asset.height,
}));
```

- [x] **Step 3：接入电脑图库导入。** 在 `App.tsx` 导入 `libraryReferenceSources`，并将图库 `onUse` 中成功导入时的 `replaceReferences` 调用替换为：

```ts
replaceReferences([...references, {
  id: uploaded.id,
  assetId: uploaded.id,
  name: uploaded.filename,
  ...libraryReferenceSources(api, image),
  width: uploaded.width,
  height: uploaded.height,
}]);
```

- [x] **Step 4：实现缩略图点击预览。** 在 `ReferenceImageStrip` 中添加 `selectedId` 状态，并从当前 `items` 按 id 查找 `selected`。将原缩略图位置的图片换成以下按钮，并在列表末尾加入弹窗。引入 `Modal`、`SafeAreaView`、`useState` 和现有 `ZoomableImage`：

```tsx
const [selectedId, setSelectedId] = useState<string | null>(null);
const selected = items.find((item) => item.id === selectedId);

<Pressable
  accessibilityRole="button"
  accessibilityLabel={`预览参考图 ${index + 1} ${item.name}`}
  onPress={() => setSelectedId(item.id)}
>
  <Image source={item.thumbnailSource} style={styles.thumb} />
</Pressable>

<Modal
  visible={selected !== undefined}
  animationType="slide"
  onRequestClose={() => setSelectedId(null)}
>
  <SafeAreaView style={styles.viewer}>
    <View style={styles.viewerHeader}>
      <Text numberOfLines={1} style={styles.viewerTitle}>{selected?.name}</Text>
      <Pressable accessibilityLabel="关闭参考图预览" onPress={() => setSelectedId(null)}>
        <Text style={styles.viewerClose}>关闭</Text>
      </Pressable>
    </View>
    {selected && <ZoomableImage key={selected.id} source={selected.previewSource} />}
  </SafeAreaView>
</Modal>
```

为 `viewer` 设置 `flex: 1`、深色背景；`viewerHeader` 设置横向布局及可见的关闭按钮。弹窗应是 `ReferenceImageStrip` 根 `View` 的最后一个子节点，不插入每张图片的 `map` 内。删除图片后，按 id 查找的预览对象消失。
- [x] **Step 5：核对预览交互。** 现有 `ZoomableImage` 已支持 1–4 倍双指缩放和放大后单指拖动；无需另建手势逻辑。缩略图按钮与移动、删除、插入 `<Picture N>` 按钮相互独立。

## Task 3：验证与交付

**Files:**

- Modify: `task_plan.md`
- Modify: `findings.md`
- Modify: `progress.md`

- [x] **Step 1：运行自动检查。** 在 `apps/mobile` 依次运行 `npm test`、`npm run typecheck`、`npm run export`；预期全部退出码为 0。若导出超时，遵守仓库 `AGENTS.md` 的最多三次尝试限制。
- [ ] **Step 2：在可用设备上手动验收。** 从电脑图库选择图片，返回生成页确认 72×72 缩略图显示实际画面；点击后确认原图、双指放大缩小、放大后单指拖动、关闭及 Android 返回键。再用手机相册选一张图重复检查，并核对参考图移动和删除后预览仍对应当前图片。
- [x] **Step 3：记录证据和限制。** 更新计划与进度文件，注明自动检查结果、设备实测结果，以及设备不可用时尚未完成的实测项。交付时明确说明实际验证范围。

## 自检

- 覆盖电脑图库缩略图、手机缩略图、点击预览、缩放、拖动、关闭，以及受保护媒体请求。
- 不新增服务端接口；沿用图库现有 `thumbnail_url` 与 `content_url`。
- 新增来源函数的输入与返回字段在测试、组件和调用处保持一致。

## 2026-09-25 执行结果

- 基线手机端测试：24/24 通过。
- 新增图片来源测试先失败（缺少实现），实现后 2/2 通过；完整测试 26/26 通过。
- `npm run typecheck`、`npm run export`、`git diff --check` 通过。
- 根据 `README.md` 的安装说明，额外重建 `app-release.apk`。首次因 `ANDROID_HOME` 未设置失败，确认本机 SDK 路径后第二次构建成功；APK v2 签名验证通过。
- ADB 当前无在线设备；Task 3 Step 2 的手机画面和手势验收仍待执行。

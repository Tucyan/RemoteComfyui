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

import Image from '@tiptap/extension-image';
import { ReactNodeViewRenderer } from '@tiptap/react';
import { ResizableImageComponent } from './ResizableImage';

export const ResizableImageExtension = Image.extend({
  addNodeView() {
    return ReactNodeViewRenderer(ResizableImageComponent);
  },
});

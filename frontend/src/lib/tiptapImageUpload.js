import { Plugin, PluginKey } from 'prosemirror-state';

function findImageBySrc(state, src) {
  let pos = null;
  state.doc.descendants((node, p) => {
    if (node.type.name === 'image' && node.attrs.src === src) {
      pos = p;
      return false;
    }
  });
  return pos;
}

function validateImage(file) {
  if (file.size > 5 * 1024 * 1024) {
    alert("File size exceeds 5MB limit.");
    return false;
  }
  if (file.type === "image/gif" || file.type === "image/svg+xml") {
    alert("GIF and SVG formats are not allowed.");
    return false;
  }
  if (!file.type.startsWith("image/")) {
    alert("Only image files are allowed.");
    return false;
  }
  return true;
}

function buildHeaders() {
  const headers = {};
  const token = localStorage.getItem('token');
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const csrfMatch = document.cookie.match(/(?:^|;\s*)csrf_token=([^;]*)/);
  if (csrfMatch && csrfMatch[1]) {
    headers['X-CSRF-Token'] = decodeURIComponent(csrfMatch[1]);
  }
  return headers;
}

async function uploadFile(file, endpoint) {
  const formData = new FormData();
  formData.append('file', file);
  const res = await fetch(endpoint, { method: 'POST', headers: buildHeaders(), body: formData });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || "Failed to upload image");
  }
  return res.json();
}

export const handleImageUploadFlow = async (file, id, endpointPrefix = 'resources') => {
  if (!validateImage(file)) return null;
  try {
    const data = await uploadFile(file, `/api/${endpointPrefix}/${id}/upload-image`);
    return data.url;
  } catch (e) {
    alert(e.message);
    return null;
  }
};

async function uploadAndReplace(view, file, localUrl, endpoint) {
  let success = false;
  try {
    const data = await uploadFile(file, endpoint);
    const pos = findImageBySrc(view.state, localUrl);
    if (pos !== null) {
      const tr2 = view.state.tr.setNodeMarkup(pos, null, { src: data.url, alt: null });
      view.dispatch(tr2);
    }
    success = true;
    return data.url;
  } catch (e) {
    alert(e.message);
  } finally {
    URL.revokeObjectURL(localUrl);
    if (!success) {
      const pos = findImageBySrc(view.state, localUrl);
      if (pos !== null) {
        view.dispatch(view.state.tr.delete(pos, pos + 1));
      }
    }
  }
  return null;
}

export const ImageUploadPlugin = (id, endpointPrefix) => {
  const endpoint = `/api/${endpointPrefix}/${id}/upload-image`;

  return new Plugin({
    key: new PluginKey('imageUpload'),
    props: {
      handlePaste(view, event) {
        const items = Array.from(event.clipboardData?.items || []);
        for (const item of items) {
          if (item.type.indexOf('image') !== 0) continue;
          event.preventDefault();
          const file = item.getAsFile();
          if (!file || !validateImage(file)) return true;

          const localUrl = URL.createObjectURL(file);
          const { schema } = view.state;
          const node = schema.nodes.image.create({ src: localUrl });
          view.dispatch(view.state.tr.replaceSelectionWith(node));
          uploadAndReplace(view, file, localUrl, endpoint);
          return true;
        }
        return false;
      },

      handleDrop(view, event, _slice, moved) {
        if (moved || !event.dataTransfer?.files?.[0]) return false;
        const file = event.dataTransfer.files[0];
        if (file.type.indexOf('image') !== 0) return false;
        event.preventDefault();

        const coordinates = view.posAtCoords({ left: event.clientX, top: event.clientY });
        if (!coordinates) return true;

        const localUrl = URL.createObjectURL(file);
        const { schema } = view.state;
        const node = schema.nodes.image.create({ src: localUrl });
        view.dispatch(view.state.tr.insert(coordinates.pos, node));
        uploadAndReplace(view, file, localUrl, endpoint);
        return true;
      }
    }
  });
};

import { Extension } from '@tiptap/core';

export const ImageUploadExtension = Extension.create({
  name: 'imageUpload',

  addOptions() {
    return {
      id: null,
      endpointPrefix: 'resources'
    };
  },

  addProseMirrorPlugins() {
    return [
      ImageUploadPlugin(this.options.id, this.options.endpointPrefix)
    ];
  }
});

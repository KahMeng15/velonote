import { NodeViewWrapper } from '@tiptap/react';
import { ActionIcon, Group, Tooltip, Paper, Text, Skeleton } from '@mantine/core';
import { useState } from 'react';

export const ResizableImageComponent = (props) => {
  const { node, updateAttributes, selected } = props;
  const src = node.attrs.src;
  const [loaded, setLoaded] = useState(false);
  
  // Extract size from hash or default to medium
  let currentSize = 'medium';
  if (src.endsWith('#small')) currentSize = 'small';
  if (src.endsWith('#large')) currentSize = 'large';

  const setSize = (size) => {
    const baseSrc = src.split('#')[0];
    const newSrc = size === 'medium' ? baseSrc : `${baseSrc}#${size}`;
    updateAttributes({ src: newSrc });
  };

  let maxWidth = '100%';
  if (currentSize === 'small') maxWidth = '33%';
  if (currentSize === 'large') maxWidth = '100%';
  if (currentSize === 'medium') maxWidth = '66%';

  return (
    <NodeViewWrapper style={{ display: 'inline-block', position: 'relative', maxWidth: '100%', width: maxWidth }}>
      {!loaded && (
        <Skeleton height={200} width="100%" radius="md" animate style={{ margin: '1rem 0' }} />
      )}
      <img
        src={src}
        alt={node.attrs.alt}
        title={node.attrs.title}
        loading="lazy"
        onLoad={() => setLoaded(true)}
        data-drag-handle="true"
        className={selected ? 'ProseMirror-selectednode' : ''}
        onDragStart={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const clone = e.currentTarget.cloneNode(true);
          clone.style.width = `${rect.width}px`;
          clone.style.height = `${rect.height}px`;
          clone.style.maxWidth = 'none';
          clone.style.position = 'absolute';
          clone.style.top = '-9999px';
          document.body.appendChild(clone);
          e.dataTransfer.setDragImage(clone, e.nativeEvent.offsetX || rect.width / 2, e.nativeEvent.offsetY || rect.height / 2);
          setTimeout(() => {
            if (clone.parentNode) {
              clone.parentNode.removeChild(clone);
            }
          }, 0);
        }}
        style={{
          maxWidth: '100%',
          width: '100%',
          height: 'auto',
          opacity: loaded ? 1 : 0,
          position: loaded ? 'static' : 'absolute',
          pointerEvents: loaded ? 'auto' : 'none',
          borderRadius: '8px',
          margin: loaded ? '1rem 0' : 0,
          transition: 'max-width 0.2s ease',
          boxShadow: selected ? '0 0 0 2px var(--mantine-color-blue-5)' : 'none'
        }}
      />
      {selected && (
        <Paper
          shadow="sm"
          p={4}
          withBorder
          style={{
            position: 'absolute',
            bottom: '10px',
            left: '50%',
            transform: 'translateX(-50%)',
            zIndex: 10,
            backgroundColor: 'rgba(255, 255, 255, 0.9)',
            backdropFilter: 'blur(4px)'
          }}
        >
          <Group gap={4}>
            <Tooltip label="Small (33%)">
              <ActionIcon
                size="sm"
                variant={currentSize === 'small' ? 'filled' : 'subtle'}
                onClick={() => setSize('small')}
              >
                <Text size="xs" fw={700}>S</Text>
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Medium (66%)">
              <ActionIcon
                size="sm"
                variant={currentSize === 'medium' ? 'filled' : 'subtle'}
                onClick={() => setSize('medium')}
              >
                <Text size="xs" fw={700}>M</Text>
              </ActionIcon>
            </Tooltip>
            <Tooltip label="Large (100%)">
              <ActionIcon
                size="sm"
                variant={currentSize === 'large' ? 'filled' : 'subtle'}
                onClick={() => setSize('large')}
              >
                <Text size="xs" fw={700}>L</Text>
              </ActionIcon>
            </Tooltip>
          </Group>
        </Paper>
      )}
    </NodeViewWrapper>
  );
};

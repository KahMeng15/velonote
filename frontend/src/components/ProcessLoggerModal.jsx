import React, { useState, useEffect, useRef, useCallback } from "react";
import { Modal, Text, ScrollArea, Code, ActionIcon, Group, Badge, Tooltip } from "@mantine/core";
import { IconX, IconTerminal, IconRefresh } from "@tabler/icons-react";
import { fetchApi } from "../lib/api";

const POLL_INTERVAL_MS = 3000; // poll every 3s while a task is active

export default function ProcessLoggerModal({ opened, onClose, entityId, tasks, entityType }) {
  const [logs, setLogs] = useState("");
  const [lastFetch, setLastFetch] = useState(null);
  const [isLive, setIsLive] = useState(false);
  const scrollRef = useRef(null);
  const pollTimerRef = useRef(null);

  // Determine if there is an active task for this entity
  // Entity IDs are nested inside input_data.kwargs (e.g. resource_id, exercise_id, note_id)
  const hasActiveTask = tasks && tasks.some(
    (t) => {
      const kwargs = t.input_data?.kwargs || {};
      const taskEntityId = kwargs.resource_id || kwargs.exercise_id || kwargs.note_id || kwargs.summary_id || "";
      return taskEntityId === entityId &&
        (t.status === "pending" || t.status === "running" || t.status === "processing");
    }
  );

  const fetchLogs = useCallback(() => {
    if (!entityId) return;
    fetchApi(`/logs/${entityId}`)
      .then((data) => {
        if (data && data.logs) {
          setLogs(data.logs);
        } else if (data && data.logs === "") {
          setLogs("No log entries yet — processing may not have started.\n");
        }
        setLastFetch(new Date());
      })
      .catch((err) => {
        console.error("Failed to fetch logs:", err);
      });
  }, [entityId]);

  // Fetch logs when modal opens
  useEffect(() => {
    if (opened && entityId) {
      setLogs("");
      fetchLogs();
    }
  }, [opened, entityId, fetchLogs]);

  // Poll while a task is active
  useEffect(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }

    if (opened && entityId && hasActiveTask) {
      setIsLive(true);
      pollTimerRef.current = setInterval(fetchLogs, POLL_INTERVAL_MS);
    } else {
      setIsLive(false);
    }

    return () => {
      if (pollTimerRef.current) {
        clearInterval(pollTimerRef.current);
        pollTimerRef.current = null;
      }
    };
  }, [opened, entityId, hasActiveTask, fetchLogs]);

  // Also listen for websocket process_log events for instant updates
  useEffect(() => {
    const handleLogEvent = (event) => {
      const payload = event.detail;
      if (payload && payload.entity_id === entityId) {
        // Re-fetch the full log from server to keep in sync
        fetchLogs();
      }
    };
    window.addEventListener("ws_message", handleLogEvent);
    return () => window.removeEventListener("ws_message", handleLogEvent);
  }, [entityId, fetchLogs]);

  // Auto-scroll to bottom when logs update
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [logs]);

  const formatTimestamp = (d) => {
    if (!d) return "";
    return d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
  };

  return (
    <Modal
      opened={opened}
      onClose={onClose}
      title={
        <Group gap="xs">
          <IconTerminal size={20} />
          <Text fw={600}>Processing Logs</Text>
          {isLive && (
            <Badge color="green" size="xs" variant="dot">
              LIVE
            </Badge>
          )}
          {lastFetch && (
            <Text size="xs" c="dimmed" ml={4}>
              Updated {formatTimestamp(lastFetch)}
            </Text>
          )}
        </Group>
      }
      size="xl"
      withCloseButton={false}
      styles={{
        header: { backgroundColor: "#1A1B1E", borderBottom: "1px solid #2C2E33", color: "white" },
        body: { backgroundColor: "#141517", padding: 0 },
      }}
    >
      <div style={{ position: "relative" }}>
        <Group style={{ position: "absolute", top: -47, right: 10, gap: 4 }}>
          <Tooltip label="Refresh logs">
            <ActionIcon
              onClick={fetchLogs}
              variant="transparent"
              style={{ color: "#A6A7AB" }}
              size="sm"
            >
              <IconRefresh size={16} />
            </ActionIcon>
          </Tooltip>
          <ActionIcon
            onClick={onClose}
            style={{ color: "white" }}
            variant="transparent"
          >
            <IconX size={20} />
          </ActionIcon>
        </Group>
        <ScrollArea h={500} viewportRef={scrollRef} p="md">
          <Code
            block
            color="dark"
            style={{
              backgroundColor: "transparent",
              color: "#A6A7AB",
              fontSize: 12,
              whiteSpace: "pre-wrap",
              wordBreak: "break-all",
            }}
          >
            {logs || "No log entries yet. Start processing to see logs here."}
          </Code>
        </ScrollArea>
      </div>
    </Modal>
  );
}

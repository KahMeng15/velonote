import re

filepath = "SummaryView.jsx"
with open(filepath, "r") as f:
    content = f.read()

# 1. Update useParams
content = re.sub(
    r'const { noteId, summaryId } = useParams\(\);',
    r'const { summaryId } = useParams();',
    content
)

# 2. Update useEffect to fetch summary then note
new_use_effect = """  useEffect(() => {
    if (!summaryId) {
      navigate('/dashboard');
      return;
    }
    
    const init = async () => {
      try {
        setLoading(true);
        const summaryData = await fetchApi(`/summaries/${summaryId}`);
        setSelectedSummary(summaryData);
        setSummaryContent(summaryData.content);
        
        const noteData = await fetchApi(`/notes/${summaryData.note_id}`);
        setNote(noteData);
        setLoading(false);
      } catch (err) {
        console.error("Failed to load data", err);
        setError("Failed to load summary");
        setLoading(false);
      }
    };
    init();
  }, [summaryId]);"""

content = re.sub(r'  useEffect\(\(\) => \{\n    if \(!noteId\).*?}, \[noteId\]\);', new_use_effect, content, flags=re.DOTALL)

# 3. Strip out the rest of the unnecessary useEffects/functions
content = re.sub(r'  const loadSummaries = async \(.*?\};', '', content, flags=re.DOTALL)
content = re.sub(r'  const loadSummaryContent = async \(.*?\};', '', content, flags=re.DOTALL)
content = re.sub(r'  const checkTaskStatus = async \(.*?\};', '', content, flags=re.DOTALL)
content = re.sub(r'  useEffect\(\(\) => \{\n    let interval;\n    if \(generating.*?}, \[generating, currentTaskId\]\);', '', content, flags=re.DOTALL)
content = re.sub(r'  const startGenerateSummary = async \(.*?\};', '', content, flags=re.DOTALL)

# 4. Remove unnecessary UI elements from Sidebar
content = re.sub(r'<Tooltip label="Generate".*?</Tooltip>', '', content, flags=re.DOTALL)
content = re.sub(r'<Tooltip label="Back to note".*?</Tooltip>', '', content, flags=re.DOTALL)

# Remove the Versions section and the summaries.map(...)
content = re.sub(r'\{\!isEditing && \(\n                <>\n                  \{sidebarOpen && <Title order=\{5\} fw=\{600\} c="dimmed" mt="xl" mb="md">Versions</Title>\}.*?\{/\* Modals \*/\}', '{/* Modals */}', content, flags=re.DOTALL)

# 5. Fix breadcrumbs top bar
breadcrumb_replacement = """          <Group>
            {note?.subject && (
              <Group gap="xs" ml="xs">
                {note.subject.group && (
                  <>
                    <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/group/${note.subject.group.id}`)}>{note.subject.group.name}</Text>
                    <Text size="sm" c="dimmed">/</Text>
                  </>
                )}
                <Text size="sm" fw={500} c="dimmed" className="clickable-crumb" onClick={() => navigate(`/subject/${note.subject.id}`)}>{note.subject.name}</Text>
              </Group>
            )}
          </Group>"""
content = re.sub(r'<Group>\s*<ActionIcon variant="subtle".*?{note\?.subject && \(.*?</Group>\s*</Group>\s*</Group>', breadcrumb_replacement + '\n        </Group>', content, flags=re.DOTALL)

# 6. Change noteId check for render to note check
content = re.sub(r'if \(!noteId\) return null;', r'if (!summaryId) return null;', content)

# 7. Also remove `generatingSummaryId`, `currentTaskId`, `generating` states if they are around line 130
content = re.sub(r'  const \[generating, setGenerating\] = useState\(false\);\n', '', content)
content = re.sub(r'  const \[generatingSummaryId, setGeneratingSummaryId\] = useState\(null\);\n', '', content)
content = re.sub(r'  const \[currentTaskId, setCurrentTaskId\] = useState\(null\);\n', '', content)
content = re.sub(r'  const \[taskStatus, setTaskStatus\] = useState\(null\);\n', '', content)

with open(filepath, "w") as f:
    f.write(content)
print("Patched SummaryView.jsx")

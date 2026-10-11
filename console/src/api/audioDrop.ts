const AUDIO_EXT =
  /\.(mp3|wav|wave|flac|ogg|oga|opus|m4a|aac|aiff|aif|wma|mp2|webm)$/i;

const UPLOAD_CHUNK = 4;

export function isFileDrag(event: { dataTransfer: DataTransfer | null }): boolean {
  return Array.from(event.dataTransfer?.types ?? []).includes("Files");
}

export function isAudioFile(file: File): boolean {
  if (file.size <= 0) return false;
  const name = file.name.split(/[/\\]/).pop() ?? file.name;
  if (name.startsWith(".")) return false;
  if (file.type.startsWith("audio/")) return true;
  return AUDIO_EXT.test(name);
}

export function audioFilesFromList(list: FileList | File[]): File[] {
  return Array.from(list).filter(isAudioFile);
}

export function chunkFiles<T>(items: T[], size = UPLOAD_CHUNK): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

function readFile(entry: FileSystemFileEntry): Promise<File> {
  return new Promise((resolve, reject) => {
    entry.file(resolve, reject);
  });
}

async function readDirectory(entry: FileSystemDirectoryEntry): Promise<File[]> {
  const reader = entry.createReader();
  const files: File[] = [];
  const readBatch = () =>
    new Promise<FileSystemEntry[]>((resolve, reject) => {
      reader.readEntries(resolve, reject);
    });
  let batch: FileSystemEntry[];
  do {
    batch = await readBatch();
    const nested = await Promise.all(
      batch.map(async (child) => {
        if (child.isFile) return [await readFile(child as FileSystemFileEntry)];
        if (child.isDirectory) {
          return readDirectory(child as FileSystemDirectoryEntry);
        }
        return [];
      }),
    );
    for (const group of nested) files.push(...group);
  } while (batch.length > 0);
  return files;
}

/** Files from a drop, folders walked. `keep` picks them: audio only unless the caller sorts them itself. */
export async function filesFromDataTransfer(
  data: DataTransfer,
  keep: (file: File) => boolean = isAudioFile,
): Promise<File[]> {
  const items = Array.from(data.items ?? []);
  const fromEntries: File[] = [];
  let sawEntry = false;
  for (const item of items) {
    if (item.kind !== "file") continue;
    const entry = item.webkitGetAsEntry?.();
    if (!entry) continue;
    sawEntry = true;
    if (entry.isDirectory) {
      fromEntries.push(...(await readDirectory(entry as FileSystemDirectoryEntry)));
    } else if (entry.isFile) {
      fromEntries.push(await readFile(entry as FileSystemFileEntry));
    }
  }
  const raw = sawEntry ? fromEntries : Array.from(data.files ?? []);
  return raw.filter(keep);
}

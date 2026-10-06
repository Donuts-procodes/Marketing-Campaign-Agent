import { useRef, useState } from "react";
import { FileText, UploadCloud, X } from "lucide-react";
import { cn } from "@/lib/utils";

interface DossierUploadProps {
  files: File[];
  onFilesChange: (files: File[]) => void;
  disabled?: boolean;
}

const ACCEPTED_EXTENSIONS = [".pdf", ".txt", ".md", ".json", ".docx", ".xlsx", ".xls", ".csv"];
// Mirrors the server limits (MAX_UPLOAD_FILES, MAX_DOSSIER_BYTES).
const MAX_FILES = 10;
const MAX_TOTAL_BYTES = 15 * 1024 * 1024;

const fileKey = (f: File) => `${f.name}:${f.size}:${f.lastModified}`;

export function DossierUpload({ files, onFilesChange, disabled = false }: DossierUploadProps) {
  const [isDragOver, setIsDragOver] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const addFiles = (incoming: FileList | null) => {
    if (!incoming || incoming.length === 0) return;
    setErrorMessage(null);
    const known = new Set(files.map(fileKey));
    const next = [...files];
    for (const file of Array.from(incoming)) {
      const ext = "." + (file.name.split(".").pop() ?? "").toLowerCase();
      if (!ACCEPTED_EXTENSIONS.includes(ext)) {
        setErrorMessage(`"${file.name}" skipped: allowed types are ${ACCEPTED_EXTENSIONS.join(", ")}`);
        continue;
      }
      if (!known.has(fileKey(file))) {
        known.add(fileKey(file));
        next.push(file);
      }
    }
    if (next.length > MAX_FILES) {
      setErrorMessage(`At most ${MAX_FILES} files.`);
      return;
    }
    if (next.reduce((sum, f) => sum + f.size, 0) > MAX_TOTAL_BYTES) {
      setErrorMessage("Files exceed the 15 MB total limit.");
      return;
    }
    onFilesChange(next);
  };

  const removeFile = (index: number) => {
    setErrorMessage(null);
    onFilesChange(files.filter((_, i) => i !== index));
  };

  const totalKb = files.reduce((sum, f) => sum + f.size, 0) / 1024;

  return (
    <div className="w-full space-y-2">
      <div className="flex items-center justify-between">
        <label className="text-xs font-bold text-[#19191B]">Product documents (optional)</label>
        <span className="text-[11px] text-zinc-500">
          PDF, DOCX, TXT, MD, JSON · up to {MAX_FILES} files, 15 MB total
        </span>
      </div>

      <div
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && inputRef.current?.click()}
        onKeyDown={(e) => {
          if (!disabled && (e.key === "Enter" || e.key === " ")) {
            e.preventDefault();
            inputRef.current?.click();
          }
        }}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setIsDragOver(true);
        }}
        onDragLeave={(e) => {
          e.preventDefault();
          setIsDragOver(false);
        }}
        onDrop={(e) => {
          e.preventDefault();
          setIsDragOver(false);
          if (!disabled) addFiles(e.dataTransfer.files);
        }}
        className={cn(
          "border-2 border-dashed rounded-2xl p-5 transition cursor-pointer flex flex-col items-center justify-center text-center gap-1.5",
          isDragOver ? "border-[#19191B] bg-[#F8B4D9]/20" : "border-[#EDE7D8] bg-[#FAF7EE] hover:border-zinc-400",
          disabled && "opacity-50 cursor-not-allowed"
        )}
      >
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPTED_EXTENSIONS.join(",")}
          className="hidden"
          disabled={disabled}
          onChange={(e) => {
            addFiles(e.target.files);
            e.target.value = ""; // allow re-selecting the same file after removing it
          }}
        />
        <UploadCloud className="w-6 h-6 text-zinc-500" />
        <p className="text-xs text-zinc-600">
          <span className="font-bold text-[#19191B]">Click to add files</span> or drag and drop
        </p>
        <p className="text-[11px] text-zinc-500">Briefs, pitch decks, product sheets: used for autofill and research</p>
      </div>

      {files.length > 0 && (
        <ul className="space-y-1.5">
          {files.map((file, index) => (
            <li
              key={fileKey(file)}
              className="flex items-center justify-between gap-3 px-3 py-2 rounded-xl bg-white border border-[#EDE7D8]"
            >
              <span className="flex items-center gap-2 min-w-0">
                <FileText className="w-4 h-4 shrink-0 text-zinc-500" />
                <span className="text-xs font-semibold text-[#19191B] truncate">{file.name}</span>
                <span className="text-[11px] text-zinc-500 shrink-0">{(file.size / 1024).toFixed(1)} KB</span>
              </span>
              <button
                type="button"
                onClick={() => removeFile(index)}
                disabled={disabled}
                aria-label={`Remove ${file.name}`}
                className="p-1 rounded-md text-zinc-400 hover:text-rose-600 hover:bg-rose-50 transition"
              >
                <X className="w-4 h-4" />
              </button>
            </li>
          ))}
          <li className="text-[11px] text-zinc-500 px-1">
            {files.length} file{files.length === 1 ? "" : "s"} · {totalKb.toFixed(1)} KB total
          </li>
        </ul>
      )}

      {errorMessage && <p className="text-xs font-medium text-rose-600">{errorMessage}</p>}
    </div>
  );
}

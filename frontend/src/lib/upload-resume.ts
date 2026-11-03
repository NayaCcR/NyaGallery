const DATABASE_NAME = "nya-upload-resume";
const STORE_NAME = "uploads";

export type PersistedUpload = {
  id: string;
  file: File;
  title: string;
  artist: string;
  sourceId: string;
  tags: string[];
  uploadId?: string;
  rotation?: 0 | 90 | 180 | 270;
  cropLeft?: number;
  cropTop?: number;
  cropRight?: number;
  cropBottom?: number;
  flipHorizontal?: boolean;
  flipVertical?: boolean;
  exifPolicy?: "keep" | "strip";
};

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DATABASE_NAME, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(STORE_NAME, { keyPath: "id" });
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Could not open upload persistence"));
  });
}

async function run<T>(mode: IDBTransactionMode, operation: (store: IDBObjectStore) => IDBRequest<T>): Promise<T> {
  const database = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = database.transaction(STORE_NAME, mode);
    const request = operation(transaction.objectStore(STORE_NAME));
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("Upload persistence failed"));
    transaction.oncomplete = () => database.close();
    transaction.onerror = () => {
      database.close();
      reject(transaction.error ?? new Error("Upload persistence transaction failed"));
    };
  });
}

export const uploadResumeStore = {
  list: () => run<PersistedUpload[]>("readonly", (store) => store.getAll()),
  put: (upload: PersistedUpload) => run<IDBValidKey>("readwrite", (store) => store.put(upload)),
  remove: (id: string) => run<undefined>("readwrite", (store) => store.delete(id)),
};

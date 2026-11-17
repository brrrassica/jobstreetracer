import { DEFAULT_SETTINGS, type Job, type Run, type Search, type Settings } from "./types";

const DB_NAME = "jobstreetracer";
const DB_VERSION = 1;
const SETTINGS_KEY = "app";

let dbPromise: Promise<IDBDatabase> | null = null;

function openDb(): Promise<IDBDatabase> {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, DB_VERSION);
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains("jobs")) {
        const jobs = db.createObjectStore("jobs", { keyPath: "id" });
        jobs.createIndex("firstSeen", "firstSeen");
        jobs.createIndex("searchName", "searchName");
        jobs.createIndex("company", "company");
        jobs.createIndex("status", "tracking.status");
      }
      if (!db.objectStoreNames.contains("searches")) {
        db.createObjectStore("searches", { keyPath: "name" });
      }
      if (!db.objectStoreNames.contains("runs")) {
        db.createObjectStore("runs", { keyPath: "key" });
      }
      if (!db.objectStoreNames.contains("settings")) {
        db.createObjectStore("settings", { keyPath: "key" });
      }
      if (!db.objectStoreNames.contains("meta")) {
        db.createObjectStore("meta", { keyPath: "key" });
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("indexedDB open failed"));
  });
  return dbPromise;
}

function done<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error ?? new Error("indexedDB request failed"));
  });
}

export async function dbGetAll<T>(store: string): Promise<T[]> {
  const db = await openDb();
  const tx = db.transaction(store, "readonly");
  return done(tx.objectStore(store).getAll() as IDBRequest<T[]>);
}

export async function dbGet<T>(store: string, key: IDBValidKey): Promise<T | undefined> {
  const db = await openDb();
  const tx = db.transaction(store, "readonly");
  return done(tx.objectStore(store).get(key) as IDBRequest<T | undefined>);
}

export async function dbPut<T>(store: string, value: T): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(store, "readwrite");
  tx.objectStore(store).put(value as unknown as object);
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("indexedDB write failed"));
  });
}

export async function dbBulkPut<T>(store: string, values: T[]): Promise<void> {
  if (values.length === 0) return;
  const db = await openDb();
  const tx = db.transaction(store, "readwrite");
  const objectStore = tx.objectStore(store);
  for (const value of values) objectStore.put(value as unknown as object);
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("indexedDB bulk write failed"));
  });
}

export async function dbDelete(store: string, key: IDBValidKey): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(store, "readwrite");
  tx.objectStore(store).delete(key);
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("indexedDB delete failed"));
  });
}

export async function dbClear(store: string): Promise<void> {
  const db = await openDb();
  const tx = db.transaction(store, "readwrite");
  tx.objectStore(store).clear();
  await new Promise<void>((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error ?? new Error("indexedDB clear failed"));
  });
}

export async function getSettings(): Promise<Settings> {
  const row = await dbGet<{ key: string; value: Settings }>("settings", SETTINGS_KEY);
  return {
    ...DEFAULT_SETTINGS,
    ...(row?.value ?? {}),
    telegram: { ...DEFAULT_SETTINGS.telegram, ...(row?.value?.telegram ?? {}) },
  };
}

export async function saveSettings(settings: Settings): Promise<void> {
  await dbPut("settings", { key: SETTINGS_KEY, value: settings });
}

export async function getMeta(key: string): Promise<string | undefined> {
  const row = await dbGet<{ key: string; value: string }>("meta", key);
  return row?.value;
}

export async function setMeta(key: string, value: string): Promise<void> {
  await dbPut("meta", { key, value });
}

export interface Snapshot {
  jobs: Job[];
  searches: Search[];
  runs: Run[];
  settings: Settings;
}

export async function loadSnapshot(): Promise<Snapshot> {
  const [jobs, searches, runs, settings] = await Promise.all([
    dbGetAll<Job>("jobs"),
    dbGetAll<Search>("searches"),
    dbGetAll<Run>("runs"),
    getSettings(),
  ]);
  return { jobs, searches, runs, settings };
}

import {mergeLibraries, validateLibrary} from './library-import.ts';
import type {Library} from './types.ts';

const databaseName = 'ielts-reading-notebook-v1';
const storeName = 'libraries';
const personalKey = 'personal';

function openDatabase(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(databaseName, 1);
    request.onupgradeneeded = () => request.result.createObjectStore(storeName);
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

export async function readPersonalLibrary(): Promise<Library | null> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const request = db.transaction(storeName).objectStore(storeName).get(personalKey);
    request.onsuccess = () => {
      db.close();
      try { resolve(request.result ? validateLibrary(request.result, true) : null); }
      catch (error) { reject(error); }
    };
    request.onerror = () => { db.close(); reject(request.error); };
  });
}

export async function addPersonalLibrary(incoming: Library): Promise<Library> {
  const db = await openDatabase();
  return new Promise((resolve, reject) => {
    const transaction = db.transaction(storeName, 'readwrite');
    const store = transaction.objectStore(storeName);
    const reading = store.get(personalKey);
    let result: Library;
    let validationError: unknown;
    reading.onsuccess = () => {
      try {
        const current = reading.result ? validateLibrary(reading.result, true) : null;
        result = mergeLibraries(current, incoming);
        store.put(result, personalKey);
      } catch (error) {
        validationError = error;
        transaction.abort();
      }
    };
    transaction.oncomplete = () => { db.close(); resolve(result); };
    transaction.onabort = () => { db.close(); reject(validationError || transaction.error); };
  });
}

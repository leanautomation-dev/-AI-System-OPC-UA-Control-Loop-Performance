import { create } from 'zustand';

export interface TagValue {
  controller: string;
  signal: string;   // PV | SP | CO
  value: number;
  status: string;
  time: string;
  tag_type?: string;
}

export interface ControllerState {
  controller: string;
  PV?: number;
  SP?: number;
  CO?: number;
  last_updated?: string;
  status?: string;
}

interface TagStore {
  tags: Record<string, TagValue>;     // key = `${controller}.${signal}`
  controllers: Record<string, ControllerState>;
  updateTag: (tag: TagValue) => void;
  updateBatch: (tags: TagValue[]) => void;
}

export const useTagStore = create<TagStore>((set, get) => ({
  tags: {},
  controllers: {},

  updateTag: (tag) => {
    const key = `${tag.controller}.${tag.signal}`;
    const newTags = { ...get().tags, [key]: tag };
    const ctrl = get().controllers[tag.controller] ?? { controller: tag.controller };
    const updatedCtrl = {
      ...ctrl,
      [tag.signal]: tag.value,
      last_updated: tag.time,
      status: tag.status,
    };
    set({
      tags: newTags,
      controllers: { ...get().controllers, [tag.controller]: updatedCtrl },
    });
  },

  updateBatch: (tags) => {
    const newTags = { ...get().tags };
    const newControllers = { ...get().controllers };
    for (const tag of tags) {
      const key = `${tag.controller}.${tag.signal}`;
      newTags[key] = tag;
      const ctrl = newControllers[tag.controller] ?? { controller: tag.controller };
      newControllers[tag.controller] = {
        ...ctrl,
        [tag.signal]: tag.value,
        last_updated: tag.time,
        status: tag.status,
      };
    }
    set({ tags: newTags, controllers: newControllers });
  },
}));

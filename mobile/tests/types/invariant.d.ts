// expo-modules-core's TypeScript sources reach into `invariant`, which ships
// no types; without this one line the tests' typecheck fails inside
// node_modules on a module nothing of ours imports directly.
declare module "invariant";

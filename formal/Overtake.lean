import Mathlib

/-!
# Formalisation of Section 6 (first group) of the revised manuscript

Model of `paper/sections/03_problem_model.tex` and the conventions of
`paper/sections/06_theory.tex` (lines 17-29).  A run of a policy is represented by the
schedule it produces: start times, server assignment and a dispatch rank `ord` that
orders the jobs started at one instant (a "phase").  Every result below holds for
every schedule that satisfies the axioms of `Sched`, so in particular for the run of
any policy, including one that knows the future.
-/

open MeasureTheory Set Finset
open scoped Classical

noncomputable section

namespace Overtake

/-- One input: a finite set `J` of jobs, `k` servers, time limit `L`.  The linear order
on `J` is the arrival order with ties broken by input order (the rank), so `j < i` is
"lower rank"; `a` is monotone along it.  (Any finite linear order is `Fin n` up to
isomorphism.) -/
structure Input (J : Type) [Fintype J] [LinearOrder J] where
  k : ℕ
  L : ℝ
  a : J → ℝ
  C : J → ℝ
  hk : 0 < k
  hL : 0 < L
  ha_nonneg : ∀ i, 0 ≤ a i
  ha_mono : Monotone a
  hC_pos : ∀ i, 0 < C i
  hC_le : ∀ i, C i ≤ L

variable {J : Type} [Fintype J] [LinearOrder J] {I : Input J}

/-- A non-preemptive work-conserving `k`-server schedule of the input `I`.
Job `j` occupies server `srv j` on the half-open interval `[s j, s j + C j)`.
`ord` is the order in which the policy starts jobs (`j ≺ i` iff `ord j < ord i`);
it is a strict total order that refines the order of start times. -/
structure Sched (I : Input J) where
  s : J → ℝ
  srv : J → Fin I.k
  ord : J → ℕ
  start_ge : ∀ i, I.a i ≤ s i
  ord_inj : Function.Injective ord
  ord_refines : ∀ i j, s j < s i → ord j < ord i
  no_overlap : ∀ i j, i ≠ j → srv i = srv j → s i + I.C i ≤ s j ∨ s j + I.C j ≤ s i
  /-- No server is idle while a job waits.  Job `i` waits at `t` iff `a i ≤ t < s i`;
  server `m` is busy at `t` iff some job on `m` has `s j ≤ t < s j + C j`. -/
  work_conserving : ∀ t, (∃ i, I.a i ≤ t ∧ t < s i) →
    ∀ m : Fin I.k, ∃ j, srv j = m ∧ s j ≤ t ∧ t < s j + I.C j

/-- FCFS: a work-conserving schedule that always starts the earliest-arrived waiting
job and starts the jobs of one phase in arrival order; equivalently its dispatch order
is the arrival order. -/
def IsFCFS (F : Sched I) : Prop := ∀ i j, F.ord j < F.ord i ↔ j < i

namespace Sched

variable (Q : Sched I)

/-- `j ≺ i`: `j` is started before `i`. -/
def prec (j i : J) : Prop := Q.ord j < Q.ord i

/-- `j` is in service at `t`. -/
def running (j : J) (t : ℝ) : Prop := Q.s j ≤ t ∧ t < Q.s j + I.C j

/-- Remaining work of `j` at `t` (equal to `C j` before `j` starts). -/
def rem (j : J) (t : ℝ) : ℝ := max 0 (min (I.C j) (Q.s j + I.C j - t))

/-- Unfinished work at `t`, counting every job with `a j ≤ t`. -/
def U (t : ℝ) : ℝ := ∑ j ∈ univ.filter (fun j => I.a j ≤ t), Q.rem j t

/-- Waiting time. -/
def W (i : J) : ℝ := Q.s i - I.a i

/-- `In_i`: total cost of the higher-rank jobs started before `i`. -/
def In (i : J) : ℝ := ∑ j ∈ univ.filter (fun j => i < j ∧ Q.prec j i), I.C j

/-- `Out_i`: total cost of the lower-rank jobs started after `i`. -/
def Out (i : J) : ℝ := ∑ j ∈ univ.filter (fun j => j < i ∧ Q.prec i j), I.C j

/-- `R^Q_i`: remaining work at `a i` of the jobs that arrived before `i`. -/
def R (i : J) : ℝ := ∑ j ∈ univ.filter (fun j => j < i), Q.rem j (I.a i)

/-- `β^Q_i`: remaining work at `s i` of the jobs started before `i` (those that have
finished contribute `0`). -/
def beta (i : J) : ℝ := ∑ j ∈ univ.filter (fun j => Q.prec j i), Q.rem j (Q.s i)

/-- Work executed on `j` during `[u, v)`. -/
def exec (j : J) (u v : ℝ) : ℝ :=
  volume.real (Ico (Q.s j) (Q.s j + I.C j) ∩ Ico u v)

end Sched

/-- `excess_P[i] = W_P[i] - W_FCFS[i]`. -/
def excess (P F : Sched I) (i : J) : ℝ := P.W i - F.W i

/-- `Δ_i` of equation (eq:delta). -/
def Delta (P F : Sched I) (i : J) : ℝ :=
  (I.k : ℝ) * (P.W i - F.W i) - (P.In i - P.Out i)

/-! ## Basic facts -/

namespace Sched

variable (Q : Sched I)

lemma rem_nonneg (j : J) (t : ℝ) : 0 ≤ Q.rem j t := le_max_left _ _

lemma rem_le_C (j : J) (t : ℝ) : Q.rem j t ≤ I.C j :=
  max_le (I.hC_pos j).le (min_le_left _ _)

lemma rem_le_L (j : J) (t : ℝ) : Q.rem j t ≤ I.L :=
  (Q.rem_le_C j t).trans (I.hC_le j)

lemma rem_of_le_s {j : J} {t : ℝ} (h : t ≤ Q.s j) : Q.rem j t = I.C j := by
  have hC := I.hC_pos j
  unfold rem
  rw [min_eq_left (by linarith), max_eq_right hC.le]

lemma rem_eq_zero_of_not_running {j : J} {t : ℝ} (hs : Q.s j ≤ t)
    (hr : ¬ Q.running j t) : Q.rem j t = 0 := by
  unfold running at hr
  push Not at hr
  have := hr hs
  unfold rem
  apply max_eq_left
  exact (min_le_right _ _).trans (by linarith)

lemma continuous_rem (j : J) : Continuous (fun t => Q.rem j t) := by
  unfold rem
  fun_prop

lemma prec_irrefl (i : J) : ¬ Q.prec i i := lt_irrefl _

lemma prec_asymm {i j : J} (h : Q.prec j i) : ¬ Q.prec i j :=
  fun h' => lt_asymm h h'

lemma prec_total {i j : J} (h : i ≠ j) : Q.prec j i ∨ Q.prec i j := by
  unfold prec
  rcases lt_trichotomy (Q.ord j) (Q.ord i) with h1 | h1 | h1
  · exact Or.inl h1
  · exact absurd (Q.ord_inj h1).symm h
  · exact Or.inr h1

/-- `j ≺ i` implies `s j ≤ s i`. -/
lemma s_le_of_prec {i j : J} (h : Q.prec j i) : Q.s j ≤ Q.s i := by
  by_contra h'
  push Not at h'
  exact Q.prec_asymm h (Q.ord_refines j i h')

/-- Per-job identity: the remaining work drops by the work executed. -/
lemma rem_sub_rem {j : J} {u v : ℝ} (huv : u ≤ v) :
    Q.rem j u - Q.rem j v = Q.exec j u v := by
  have hC := I.hC_pos j
  unfold exec rem
  rw [Set.Ico_inter_Ico, Real.volume_real_Ico]
  simp only [max_def, min_def]
  split_ifs <;> linarith

lemma exec_nonneg (j : J) (u v : ℝ) : 0 ≤ Q.exec j u v := measureReal_nonneg


lemma U_nonneg (t : ℝ) : 0 ≤ Q.U t := sum_nonneg fun j _ => Q.rem_nonneg j t

lemma sum_rem_sub {u v : ℝ} (huv : u ≤ v) :
    ∑ j, (Q.rem j u - Q.rem j v) = ∑ j, Q.exec j u v :=
  sum_congr rfl fun _ _ => Q.rem_sub_rem huv

/-! ## Work executed on one server -/

lemma disjoint_of_srv {i j : J} (hij : i ≠ j) (h : Q.srv i = Q.srv j) :
    Disjoint (Ico (Q.s i) (Q.s i + I.C i)) (Ico (Q.s j) (Q.s j + I.C j)) := by
  rw [Set.Ico_disjoint_Ico]
  rcases Q.no_overlap i j hij h with h1 | h1
  · exact (min_le_left _ _).trans (h1.trans (le_max_right _ _))
  · exact (min_le_right _ _).trans (h1.trans (le_max_left _ _))

/-- The pieces of the jobs of one server inside a set `A` have total length at most
`|A|`. -/
lemma server_sum_le (m : Fin I.k) (O : Finset (J)) (f : J → Set ℝ)
    (hf : ∀ j, f j ⊆ Ico (Q.s j) (Q.s j + I.C j)) (hmeas : ∀ j, MeasurableSet (f j))
    (A : Set ℝ) (hA : volume A ≠ ⊤) (hsub : ∀ j ∈ O, Q.srv j = m → f j ⊆ A) :
    ∑ j ∈ O.filter (fun j => Q.srv j = m), volume.real (f j) ≤ volume.real A := by
  have hdisj : ((O.filter (fun j => Q.srv j = m) : Finset (J)) :
      Set (J)).PairwiseDisjoint f := by
    intro i hi j hj hij
    simp only [Finset.coe_filter, Set.mem_ofPred_eq] at hi hj
    exact (Q.disjoint_of_srv hij (hi.2.trans hj.2.symm)).mono (hf i) (hf j)
  have hfin : ∀ j ∈ O.filter (fun j => Q.srv j = m), volume (f j) ≠ ⊤ := fun j _ =>
    ((measure_mono (hf j)).trans_lt measure_Ico_lt_top).ne
  rw [← measureReal_biUnion_finset hdisj (fun j _ => hmeas j) hfin]
  apply measureReal_mono _ hA
  intro x hx
  simp only [Set.mem_iUnion] at hx
  obtain ⟨j, hj, hx⟩ := hx
  rw [Finset.mem_filter] at hj
  exact hsub j hj.1 hj.2 hx

lemma server_exec_le (m : Fin I.k) {u v : ℝ} (huv : u ≤ v) :
    ∑ j ∈ univ.filter (fun j => Q.srv j = m), Q.exec j u v ≤ v - u := by
  have := Q.server_sum_le m univ (fun j => Ico (Q.s j) (Q.s j + I.C j) ∩ Ico u v)
    (fun j => Set.inter_subset_left) (fun j => measurableSet_Ico.inter measurableSet_Ico)
    (Ico u v) measure_Ico_lt_top.ne (fun j _ _ => Set.inter_subset_right)
  simpa [Sched.exec, huv] using this

/-- A server busy throughout `(u, v)` executes `v - u` units of work there. -/
lemma server_exec_ge (m : Fin I.k) {u v : ℝ} (huv : u ≤ v)
    (hbusy : ∀ t ∈ Ioo u v, ∃ j, Q.srv j = m ∧ Q.running j t) :
    v - u ≤ ∑ j ∈ univ.filter (fun j => Q.srv j = m), Q.exec j u v := by
  set O := univ.filter (fun j => Q.srv j = m)
  have hdisj : (O : Set (J)).PairwiseDisjoint
      (fun j => Ico (Q.s j) (Q.s j + I.C j) ∩ Ico u v) := by
    intro i hi j hj hij
    simp only [O, Finset.coe_filter, Set.mem_ofPred_eq] at hi hj
    exact (Q.disjoint_of_srv hij (hi.2.trans hj.2.symm)).mono
      Set.inter_subset_left Set.inter_subset_left
  have hfin : ∀ j ∈ O, volume (Ico (Q.s j) (Q.s j + I.C j) ∩ Ico u v) ≠ ⊤ := fun j _ =>
    ((measure_mono Set.inter_subset_right).trans_lt measure_Ico_lt_top).ne
  unfold Sched.exec
  rw [← measureReal_biUnion_finset hdisj
    (fun j _ => measurableSet_Ico.inter measurableSet_Ico) hfin]
  have hcov : Ioo u v ⊆ ⋃ j ∈ O, (Ico (Q.s j) (Q.s j + I.C j) ∩ Ico u v) := by
    intro t ht
    obtain ⟨j, hj, hr⟩ := hbusy t ht
    simp only [Set.mem_iUnion]
    exact ⟨j, by simp [O, hj], ⟨hr.1, hr.2⟩, ht.1.le, ht.2⟩
  have hU : volume (⋃ j ∈ O, (Ico (Q.s j) (Q.s j + I.C j) ∩ Ico u v)) ≠ ⊤ := by
    refine ((measure_mono ?_).trans_lt (measure_Ico_lt_top (a := u) (b := v))).ne
    intro x hx
    simp only [Set.mem_iUnion] at hx
    obtain ⟨j, _, hx⟩ := hx
    exact hx.2
  calc v - u = volume.real (Ioo u v) := by simp [huv]
    _ ≤ _ := measureReal_mono hcov hU

lemma sum_exec_le {u v : ℝ} (huv : u ≤ v) : ∑ j, Q.exec j u v ≤ (I.k : ℝ) * (v - u) := by
  rw [← Finset.sum_fiberwise univ Q.srv (fun j => Q.exec j u v)]
  calc ∑ m, ∑ j ∈ univ.filter (fun j => Q.srv j = m), Q.exec j u v
      ≤ ∑ _m : Fin I.k, (v - u) := sum_le_sum fun m _ => Q.server_exec_le m huv
    _ = (I.k : ℝ) * (v - u) := by simp [mul_sub]

lemma sum_exec_ge {u v : ℝ} (huv : u ≤ v)
    (hbusy : ∀ t ∈ Ioo u v, ∀ m, ∃ j, Q.srv j = m ∧ Q.running j t) :
    (I.k : ℝ) * (v - u) ≤ ∑ j, Q.exec j u v := by
  rw [← Finset.sum_fiberwise univ Q.srv (fun j => Q.exec j u v)]
  calc (I.k : ℝ) * (v - u) = ∑ _m : Fin I.k, (v - u) := by simp [mul_sub]
    _ ≤ _ := sum_le_sum fun m _ => Q.server_exec_ge m huv fun t ht => hbusy t ht m

/-! ## Jobs in service at one instant -/

/-- Jobs in service at `t` sit on distinct servers; if none of them uses server `m`
there are at most `k - 1` of them. -/
lemma card_running_le (t : ℝ) (m : Fin I.k) (T : Finset (J))
    (hT : ∀ j ∈ T, Q.running j t ∧ Q.srv j ≠ m) : T.card ≤ I.k - 1 := by
  have h1 : (univ.erase m).card = I.k - 1 := by simp [Finset.card_erase_of_mem]
  rw [← h1]
  apply Finset.card_le_card_of_injOn Q.srv
  · intro j hj
    simp [(hT j hj).2]
  · intro i hi j hj hij
    by_contra hne
    have hri := (hT i hi).1
    have hrj := (hT j hj).1
    unfold running at hri hrj
    rcases Q.no_overlap i j hne hij with h | h <;> linarith

lemma sum_rem_le (t : ℝ) (m : Fin I.k) (T : Finset (J))
    (hT : ∀ j ∈ T, Q.running j t ∧ Q.srv j ≠ m) :
    ∑ j ∈ T, Q.rem j t ≤ ((I.k : ℝ) - 1) * I.L := by
  have hc := Q.card_running_le t m T hT
  have hc' : (T.card : ℝ) ≤ (I.k : ℝ) - 1 := by
    have : ((T.card : ℕ) : ℝ) ≤ ((I.k - 1 : ℕ) : ℝ) := by exact_mod_cast hc
    rwa [Nat.cast_sub (Nat.succ_le_of_lt I.hk), Nat.cast_one] at this
  calc ∑ j ∈ T, Q.rem j t ≤ ∑ _j ∈ T, I.L := sum_le_sum fun j _ => Q.rem_le_L j t
    _ = (T.card : ℝ) * I.L := by simp
    _ ≤ ((I.k : ℝ) - 1) * I.L := mul_le_mul_of_nonneg_right hc' I.hL.le

/-- If some server is idle at `t`, no job waits, so the unfinished work is held by at
most `k - 1` jobs in service. -/
lemma U_le_of_idle {t : ℝ} {m : Fin I.k} (hidle : ¬ ∃ j, Q.srv j = m ∧ Q.running j t) :
    Q.U t ≤ ((I.k : ℝ) - 1) * I.L := by
  have hnw : ∀ j, I.a j ≤ t → Q.s j ≤ t := by
    intro j hj
    by_contra h
    push Not at h
    exact hidle (Q.work_conserving t ⟨j, hj, h⟩ m)
  unfold U
  rw [← Finset.sum_filter_of_ne (p := fun j => Q.running j t)]
  · apply Q.sum_rem_le t m
    intro j hj
    rw [Finset.mem_filter] at hj
    exact ⟨hj.2, fun h => hidle ⟨j, h, hj.2⟩⟩
  · intro j hj hne
    by_contra hr
    rw [Finset.mem_filter] at hj
    exact hne (Q.rem_eq_zero_of_not_running (hnw j hj.2) hr)

end Sched

/-! ## Lemma "Workload comparison" (06_theory.tex:67) -/

lemma U_sub_U (Q1 Q2 : Sched I) (t : ℝ) :
    Q1.U t - Q2.U t = ∑ j, (Q1.rem j t - Q2.rem j t) := by
  unfold Sched.U
  rw [← sum_sub_distrib, ← Finset.sum_filter_add_sum_filter_not univ (fun j => I.a j ≤ t)]
  rw [Finset.sum_eq_zero (s := univ.filter (fun j => ¬ I.a j ≤ t)), add_zero]
  intro j hj
  rw [Finset.mem_filter] at hj
  have h := not_le.mp hj.2
  rw [Q1.rem_of_le_s (by linarith [Q1.start_ge j]),
    Q2.rem_of_le_s (by linarith [Q2.start_ge j]), sub_self]

/-- One direction of the workload comparison. -/
theorem gap_le (Q1 Q2 : Sched I) (t : ℝ) : Q1.U t - Q2.U t ≤ ((I.k : ℝ) - 1) * I.L := by
  set K := ((I.k : ℝ) - 1) * I.L with hKdef
  set D : ℝ → ℝ := fun u => ∑ j, (Q1.rem j u - Q2.rem j u) with hD
  have hDU : ∀ u, D u = Q1.U u - Q2.U u := fun u => (U_sub_U Q1 Q2 u).symm
  have hDcont : Continuous D :=
    continuous_finsetSum _ fun j _ => (Q1.continuous_rem j).sub (Q2.continuous_rem j)
  have hK : 0 ≤ K := by
    have : (1 : ℝ) ≤ I.k := by exact_mod_cast I.hk
    exact mul_nonneg (by linarith) I.hL.le
  -- an instant before every start
  set u0 := min t (-(∑ j, (|Q1.s j| + |Q2.s j|)))
  have hu0 : ∀ j, u0 ≤ Q1.s j ∧ u0 ≤ Q2.s j := by
    intro j
    have hs : |Q1.s j| + |Q2.s j| ≤ ∑ j, (|Q1.s j| + |Q2.s j|) :=
      Finset.single_le_sum (f := fun j => |Q1.s j| + |Q2.s j|)
        (fun j _ => by positivity) (Finset.mem_univ j)
    have h1 := neg_abs_le (Q1.s j)
    have h2 := neg_abs_le (Q2.s j)
    have h3 : u0 ≤ -(∑ j, (|Q1.s j| + |Q2.s j|)) := min_le_right _ _
    constructor <;> linarith [abs_nonneg (Q1.s j), abs_nonneg (Q2.s j)]
  have hDu0 : D u0 = 0 := sum_eq_zero fun j _ => by
    rw [Q1.rem_of_le_s (hu0 j).1, Q2.rem_of_le_s (hu0 j).2, sub_self]
  set S := Iic t ∩ {u | D u ≤ K}
  have hScl : IsClosed S := isClosed_Iic.inter (isClosed_le hDcont continuous_const)
  have hSne : S.Nonempty := ⟨u0, Set.mem_Iic.mpr (min_le_left _ _), by simp [hDu0, hK]⟩
  have hSbdd : BddAbove S := ⟨t, fun u hu => hu.1⟩
  set t1 := sSup S
  have ht1 : t1 ∈ S := hScl.csSup_mem hSne hSbdd
  -- on (t1, t) every server of Q1 is busy
  have hbusy : ∀ u ∈ Ioo t1 t, ∀ m, ∃ j, Q1.srv j = m ∧ Q1.running j u := by
    intro u hu m
    by_contra hidle
    have h1 := Q1.U_le_of_idle hidle
    have h2 := Q2.U_nonneg u
    have huS : u ∈ S := ⟨hu.2.le, by
      show D u ≤ K
      rw [hDU]; linarith⟩
    have := le_csSup hSbdd huS
    linarith [hu.1]
  have ht1t : t1 ≤ t := ht1.1
  have hdec : D t ≤ D t1 := by
    have e1 := Q1.sum_rem_sub ht1t
    have e2 := Q2.sum_rem_sub ht1t
    have b1 := Q1.sum_exec_ge ht1t hbusy
    have b2 := Q2.sum_exec_le ht1t
    have : D t1 - D t =
        ∑ j, (Q1.rem j t1 - Q1.rem j t) - ∑ j, (Q2.rem j t1 - Q2.rem j t) := by
      simp only [hD, ← sum_sub_distrib]
      exact sum_congr rfl fun j _ => by ring
    linarith
  rw [← hDU]
  exact hdec.trans ht1.2

/-- Lemma "Workload comparison", the inequality: `|U_{Q1}(t) - U_{Q2}(t)| ≤ (k-1)L`. -/
theorem workload_comparison (Q1 Q2 : Sched I) (t : ℝ) :
    |Q1.U t - Q2.U t| ≤ ((I.k : ℝ) - 1) * I.L := by
  rw [abs_le]
  constructor
  · linarith [gap_le Q2 Q1 t]
  · exact gap_le Q1 Q2 t

/-- Lemma "Workload comparison", the case `k = 1`: every work-conserving policy has the
same unfinished work at every instant. -/
theorem workload_comparison_k1 (hk : I.k = 1) (Q1 Q2 : Sched I) (t : ℝ) :
    Q1.U t = Q2.U t := by
  have h := workload_comparison Q1 Q2 t
  rw [hk, Nat.cast_one, sub_self, zero_mul] at h
  have := abs_nonneg (Q1.U t - Q2.U t)
  have h0 : |Q1.U t - Q2.U t| = 0 := le_antisymm h this
  rw [abs_eq_zero, sub_eq_zero] at h0
  exact h0


/-! ### The strict inequality for `k ≥ 2` (Supplementary S4.1) -/

namespace Sched

variable (Q : Sched I)

lemma sum_rem_le_b (t : ℝ) (m : Fin I.k) (T : Finset (J)) (b : ℝ) (hb0 : 0 ≤ b)
    (hT : ∀ j ∈ T, Q.running j t ∧ Q.srv j ≠ m) (hb : ∀ j ∈ T, Q.rem j t ≤ b) :
    ∑ j ∈ T, Q.rem j t ≤ ((I.k : ℝ) - 1) * b := by
  have hc := Q.card_running_le t m T hT
  have hc' : (T.card : ℝ) ≤ (I.k : ℝ) - 1 := by
    have : ((T.card : ℕ) : ℝ) ≤ ((I.k - 1 : ℕ) : ℝ) := by exact_mod_cast hc
    rwa [Nat.cast_sub (Nat.succ_le_of_lt I.hk), Nat.cast_one] at this
  calc ∑ j ∈ T, Q.rem j t ≤ ∑ _j ∈ T, b := sum_le_sum hb
    _ = (T.card : ℝ) * b := by simp
    _ ≤ ((I.k : ℝ) - 1) * b := mul_le_mul_of_nonneg_right hc' hb0

lemma U_le_of_idle_b {t : ℝ} {m : Fin I.k} (b : ℝ) (hb0 : 0 ≤ b)
    (hb : ∀ j, Q.running j t → Q.rem j t ≤ b)
    (hidle : ¬ ∃ j, Q.srv j = m ∧ Q.running j t) :
    Q.U t ≤ ((I.k : ℝ) - 1) * b := by
  have hnw : ∀ j, I.a j ≤ t → Q.s j ≤ t := by
    intro j hj
    by_contra h
    push Not at h
    exact hidle (Q.work_conserving t ⟨j, hj, h⟩ m)
  unfold U
  rw [← Finset.sum_filter_of_ne (p := fun j => Q.running j t)]
  · apply Q.sum_rem_le_b t m _ b hb0
    · intro j hj
      rw [Finset.mem_filter] at hj
      exact ⟨hj.2, fun h => hidle ⟨j, h, hj.2⟩⟩
    · intro j hj
      rw [Finset.mem_filter] at hj
      exact hb j hj.2
  · intro j hj hne
    by_contra hr
    rw [Finset.mem_filter] at hj
    exact hne (Q.rem_eq_zero_of_not_running (hnw j hj.2) hr)

end Sched

/-- `D = U_{Q1} - U_{Q2}` grows by at most `k (v - u)` on `[u, v]`, and does not grow
when every server of `Q1` is busy on `(u, v)`. -/
lemma D_step (Q1 Q2 : Sched I) {u v : ℝ} (huv : u ≤ v) :
    Q1.U v - Q2.U v = Q1.U u - Q2.U u - ∑ j, Q1.exec j u v + ∑ j, Q2.exec j u v := by
  rw [U_sub_U, U_sub_U, ← Q1.sum_rem_sub huv, ← Q2.sum_rem_sub huv]
  simp only [← sum_sub_distrib, ← sum_add_distrib]
  exact sum_congr rfl fun j _ => by ring

lemma D_le_add (Q1 Q2 : Sched I) {u v : ℝ} (huv : u ≤ v) :
    Q1.U v - Q2.U v ≤ Q1.U u - Q2.U u + (I.k : ℝ) * (v - u) := by
  rw [D_step Q1 Q2 huv]
  have h1 : 0 ≤ ∑ j, Q1.exec j u v := sum_nonneg fun j _ => Q1.exec_nonneg j u v
  have h2 := Q2.sum_exec_le huv
  linarith

lemma D_le_of_busy (Q1 Q2 : Sched I) {u v : ℝ} (huv : u ≤ v)
    (hbusy : ∀ t ∈ Ioo u v, ∀ m, ∃ j, Q1.srv j = m ∧ Q1.running j t) :
    Q1.U v - Q2.U v ≤ Q1.U u - Q2.U u := by
  rw [D_step Q1 Q2 huv]
  have h1 := Q1.sum_exec_ge huv hbusy
  have h2 := Q2.sum_exec_le huv
  linarith

/-- One direction of the strict workload comparison, `k ≥ 2`. -/
theorem gap_lt (hk2 : 2 ≤ I.k) (Q1 Q2 : Sched I) (t : ℝ) :
    Q1.U t - Q2.U t < ((I.k : ℝ) - 1) * I.L := by
  set K := ((I.k : ℝ) - 1) * I.L with hKdef
  set D : ℝ → ℝ := fun u => Q1.U u - Q2.U u with hD
  have hkr : (2 : ℝ) ≤ I.k := by exact_mod_cast hk2
  have hKpos : 0 < K := mul_pos (by linarith) I.hL
  have hDcont : Continuous D := by
    have : D = fun u => ∑ j, (Q1.rem j u - Q2.rem j u) := funext fun u => U_sub_U Q1 Q2 u
    rw [this]
    exact continuous_finsetSum _ fun j _ => (Q1.continuous_rem j).sub (Q2.continuous_rem j)
  -- before every start, `D = 0`
  set u0 := -(∑ j, (|Q1.s j| + |Q2.s j|))
  have hu0 : ∀ j, u0 ≤ Q1.s j ∧ u0 ≤ Q2.s j := by
    intro j
    have hs : |Q1.s j| + |Q2.s j| ≤ ∑ j, (|Q1.s j| + |Q2.s j|) :=
      Finset.single_le_sum (f := fun j => |Q1.s j| + |Q2.s j|)
        (fun j _ => by positivity) (Finset.mem_univ j)
    have h1 := neg_abs_le (Q1.s j)
    have h2 := neg_abs_le (Q2.s j)
    constructor <;> linarith [abs_nonneg (Q1.s j), abs_nonneg (Q2.s j)]
  have hDearly : ∀ u ≤ u0, D u = 0 := by
    intro u hu
    show Q1.U u - Q2.U u = 0
    rw [U_sub_U]
    exact sum_eq_zero fun j _ => by
      rw [Q1.rem_of_le_s (hu.trans (hu0 j).1), Q2.rem_of_le_s (hu.trans (hu0 j).2), sub_self]
  by_contra hcon
  push Not at hcon
  -- the first instant at which `D ≥ K`
  set T := {u | K ≤ D u}
  have hTcl : IsClosed T := isClosed_le continuous_const hDcont
  have hTbdd : BddBelow T := ⟨u0, fun u hu => by
    by_contra h
    push Not at h
    have := hDearly u h.le
    simp only [T, Set.mem_ofPred_eq] at hu
    linarith⟩
  set t1 := sInf T
  have ht1 : K ≤ D t1 := hTcl.csInf_mem ⟨t, hcon⟩ hTbdd
  have hbefore : ∀ u < t1, D u < K := by
    intro u hu
    by_contra h
    push Not at h
    have := csInf_le hTbdd h
    linarith
  -- a gap `δ` free of start times of `Q1` just before `t1`
  obtain ⟨δ, hδpos, hδL, hδ⟩ : ∃ δ, 0 < δ ∧ δ ≤ I.L ∧ ∀ j, Q1.s j < t1 → Q1.s j ≤ t1 - δ := by
    by_cases hne : (univ.filter (fun j => Q1.s j < t1)).Nonempty
    · obtain ⟨j0, hj0, hmax⟩ := Finset.exists_max_image _ Q1.s hne
      rw [Finset.mem_filter] at hj0
      refine ⟨min I.L (t1 - Q1.s j0), lt_min I.hL (by linarith [hj0.2]), min_le_left _ _, ?_⟩
      intro j hj
      have := hmax j (by simp [hj])
      linarith [min_le_right I.L (t1 - Q1.s j0)]
    · refine ⟨I.L, I.hL, le_rfl, fun j hj => absurd ⟨j, by simp [hj]⟩ hne⟩
  set η := δ / 4
  have hη : 0 < η := by positivity
  by_cases hb : ∀ v ∈ Ioo (t1 - η) t1, ∀ m, ∃ j, Q1.srv j = m ∧ Q1.running j v
  · have h1 := D_le_of_busy Q1 Q2 (by linarith) hb
    have h2 := hbefore (t1 - η) (by linarith)
    simp only [D] at ht1 h2
    linarith
  · push Not at hb
    obtain ⟨v, hv, m, hidle⟩ := hb
    have hidle' : ¬ ∃ j, Q1.srv j = m ∧ Q1.running j v := by
      push Not
      exact hidle
    have hU1 := Q1.U_le_of_idle_b (I.L - δ + η) (by linarith) (by
      intro j hj
      have hs : Q1.s j ≤ t1 - δ := hδ j (by linarith [hj.1, hv.2])
      unfold Sched.rem
      apply max_le (by linarith)
      exact (min_le_right _ _).trans (by linarith [I.hC_le j, hv.1])) hidle'
    have hU2 := Q2.U_nonneg v
    have hstep := D_le_add Q1 Q2 hv.2.le
    simp only [D] at ht1
    have : (I.k : ℝ) * (t1 - v) ≤ I.k * η := by
      apply mul_le_mul_of_nonneg_left (by linarith [hv.1]) (by linarith)
    have hkd : 2 * δ ≤ (I.k : ℝ) * δ := mul_le_mul_of_nonneg_right hkr hδpos.le
    have key : ((I.k : ℝ) - 1) * (I.L - δ + η) + I.k * η < K := by
      simp only [η, hKdef]
      nlinarith
    linarith

/-- Lemma "Workload comparison", strict form for `k ≥ 2`. -/
theorem workload_comparison_strict (hk2 : 2 ≤ I.k) (Q1 Q2 : Sched I) (t : ℝ) :
    |Q1.U t - Q2.U t| < ((I.k : ℝ) - 1) * I.L := by
  rw [abs_lt]
  constructor
  · linarith [gap_lt hk2 Q2 Q1 t]
  · exact gap_lt hk2 Q1 Q2 t

/-! ## The FCFS reference is unique

`IsFCFS` characterises FCFS by its dispatch order.  Any two schedules satisfying it on
the same input have the same start times, so `W_FCFS` and `excess` do not depend on
which one is taken. -/

lemma Sched.srv_injOn_running (Q : Sched I) (t : ℝ) :
    Set.InjOn Q.srv {j | Q.running j t} := by
  intro i hi j hj hij
  by_contra hne
  have hi' : Q.running i t := hi
  have hj' : Q.running j t := hj
  unfold Sched.running at hi' hj'
  rcases Q.no_overlap i j hne hij with h | h <;> linarith

lemma fcfs_unique_aux (Fa Fb : Sched I) (hb : IsFCFS Fb) (i : J)
    (hmin : ∀ j, j < i → Fa.s j = Fb.s j) (hlt : Fa.s i < Fb.s i) : False := by
  set t := Fa.s i
  have hwait : ∃ i', I.a i' ≤ t ∧ t < Fb.s i' := ⟨i, Fa.start_ge i, hlt⟩
  choose g hg using Fb.work_conserving t hwait
  have hlt_i : ∀ m, g m < i := fun m =>
    (hb i (g m)).1 (Fb.ord_refines i (g m) (lt_of_le_of_lt (hg m).2.1 hlt))
  have hrunA : ∀ m, Fa.running (g m) t := by
    intro m
    unfold Sched.running
    rw [hmin _ (hlt_i m)]
    exact ⟨(hg m).2.1, (hg m).2.2⟩
  have hginj : Function.Injective g := by
    intro m1 m2 h
    rw [← (hg m1).1, ← (hg m2).1, h]
  have hnot : i ∉ (Finset.univ : Finset (Fin I.k)).image g := by
    simp only [Finset.mem_image, Finset.mem_univ, true_and, not_exists]
    intro m hm
    exact lt_irrefl _ (hm ▸ hlt_i m)
  have hcard : (insert i ((Finset.univ : Finset (Fin I.k)).image g)).card = I.k + 1 := by
    rw [Finset.card_insert_of_notMem hnot, Finset.card_image_of_injective _ hginj,
      Finset.card_univ, Fintype.card_fin]
  have hrun : ∀ j ∈ insert i ((Finset.univ : Finset (Fin I.k)).image g), Fa.running j t := by
    intro j hj
    rw [Finset.mem_insert, Finset.mem_image] at hj
    rcases hj with rfl | ⟨m, _, rfl⟩
    · exact ⟨le_rfl, by linarith [I.hC_pos j]⟩
    · exact hrunA m
  have hle : (insert i ((Finset.univ : Finset (Fin I.k)).image g)).card ≤ (univ : Finset (Fin I.k)).card := by
    apply Finset.card_le_card_of_injOn Fa.srv
    · intro j _
      simp
    · intro j1 hj1 j2 hj2 h
      exact Fa.srv_injOn_running t (hrun j1 hj1) (hrun j2 hj2) h
  rw [hcard, Finset.card_univ, Fintype.card_fin] at hle
  omega

/-- Two FCFS schedules of one input start every job at the same time. -/
theorem fcfs_unique (F1 F2 : Sched I) (h1 : IsFCFS F1) (h2 : IsFCFS F2) (i : J) :
    F1.s i = F2.s i := by
  by_contra hc
  obtain ⟨i0, hi0, hmin⟩ := (wellFounded_lt (α := J)).has_min {i | F1.s i ≠ F2.s i} ⟨i, hc⟩
  have hmin' : ∀ j, j < i0 → F1.s j = F2.s j := by
    intro j hj
    by_contra hne
    exact hmin j hne hj
  rcases lt_or_gt_of_ne hi0 with h | h
  · exact fcfs_unique_aux F1 F2 h2 i0 hmin' h
  · exact fcfs_unique_aux F2 F1 h1 i0 (fun j hj => (hmin' j hj).symm) h

/-! ## Theorem "Net-overtake identity" (06_theory.tex:116) -/

namespace Sched

variable (Q : Sched I)

/-- Job `i` waits throughout `[a_i, s_i)`, so all `k` servers are busy there and
`k W[i]` units of work are executed. -/
lemma sum_exec_wait (i : J) : ∑ j, Q.exec j (I.a i) (Q.s i) = (I.k : ℝ) * Q.W i := by
  apply le_antisymm
  · exact Q.sum_exec_le (Q.start_ge i)
  · apply Q.sum_exec_ge (Q.start_ge i)
    intro t ht m
    exact Q.work_conserving t ⟨i, ht.1.le, ht.2⟩ m

/-- Splitting the work executed on `j` during `[a_i, s_i)` by rank and dispatch order. -/
lemma rem_split (i j : J) :
    Q.rem j (I.a i) - Q.rem j (Q.s i) =
      (if j < i then Q.rem j (I.a i) else 0) + (if i < j ∧ Q.prec j i then I.C j else 0)
      - (if j < i ∧ Q.prec i j then I.C j else 0)
      - (if Q.prec j i then Q.rem j (Q.s i) else 0) := by
  rcases lt_trichotomy j i with hji | rfl | hij
  · rcases Q.prec_total hji.ne' with h | h
    · simp [hji, h, Q.prec_asymm h, not_lt.mpr hji.le]
    · rw [Q.rem_of_le_s (Q.s_le_of_prec h)]
      simp [hji, h, Q.prec_asymm h, not_lt.mpr hji.le]
  · rw [Q.rem_of_le_s (Q.start_ge j), Q.rem_of_le_s le_rfl]
    simp [Q.prec_irrefl]
  · rcases Q.prec_total hij.ne with h | h
    · rw [Q.rem_of_le_s ((I.ha_mono hij.le).trans (Q.start_ge j))]
      simp [hij, h, not_lt.mpr hij.le]
    · rw [Q.rem_of_le_s ((Q.start_ge i).trans (Q.s_le_of_prec h)),
        Q.rem_of_le_s (Q.s_le_of_prec h)]
      simp [hij, h, Q.prec_asymm h, not_lt.mpr hij.le]

/-- Equation (eq:busy): `k W_Q[i] = R^Q_i + In_i - Out_i - β^Q_i`. -/
theorem busy (i : J) :
    (I.k : ℝ) * Q.W i = Q.R i + Q.In i - Q.Out i - Q.beta i := by
  rw [← Q.sum_exec_wait i, ← Q.sum_rem_sub (Q.start_ge i),
    sum_congr rfl fun j _ => Q.rem_split i j]
  simp only [R, In, Out, beta, Finset.sum_filter, Finset.sum_add_distrib,
    Finset.sum_sub_distrib]

lemma beta_nonneg (i : J) : 0 ≤ Q.beta i := sum_nonneg fun _ _ => Q.rem_nonneg _ _

/-- `0 ≤ β^Q_i ≤ (k-1)L`: the jobs counted in `β` are in service at `s_i` on servers
other than the one that takes `i`. -/
lemma beta_le (i : J) : Q.beta i ≤ ((I.k : ℝ) - 1) * I.L := by
  unfold beta
  rw [← Finset.sum_filter_of_ne (p := fun j => Q.running j (Q.s i))]
  · apply Q.sum_rem_le (Q.s i) (Q.srv i)
    intro j hj
    rw [Finset.mem_filter, Finset.mem_filter] at hj
    refine ⟨hj.2, fun hsrv => ?_⟩
    have hne : j ≠ i := fun h => Q.prec_irrefl i (h ▸ hj.1.2)
    have hr := hj.2
    unfold running at hr
    have hCi := I.hC_pos i
    rcases Q.no_overlap j i hne hsrv with h | h <;> linarith
  · intro j hj hne
    by_contra hr
    rw [Finset.mem_filter] at hj
    exact hne (Q.rem_eq_zero_of_not_running (Q.s_le_of_prec hj.2) hr)

/-- At `a_i` the unfinished work is `R_i` plus the untouched jobs of rank `≥ i` that
have arrived; the latter term does not depend on the policy. -/
lemma U_at_arrival (i : J) :
    Q.U (I.a i) = Q.R i + ∑ j ∈ univ.filter (fun j => ¬ j < i ∧ I.a j ≤ I.a i), I.C j := by
  unfold U R
  rw [← Finset.sum_filter_add_sum_filter_not (univ.filter (fun j => I.a j ≤ I.a i))
    (fun j => j < i), Finset.filter_filter, Finset.filter_filter]
  congr 1
  · apply Finset.sum_congr _ fun _ _ => rfl
    ext j
    simp only [Finset.mem_filter, Finset.mem_univ, true_and, and_iff_right_iff_imp]
    exact fun h => I.ha_mono h.le
  · apply Finset.sum_congr (by ext j; simp [and_comm])
    intro j hj
    rw [Finset.mem_filter] at hj
    exact Q.rem_of_le_s ((I.ha_mono (not_lt.mp hj.2.1)).trans (Q.start_ge j))

end Sched

lemma fcfs_In {F : Sched I} (hF : IsFCFS F) (i : J) : F.In i = 0 := by
  apply Finset.sum_eq_zero
  intro j hj
  rw [Finset.mem_filter] at hj
  exact absurd ((hF i j).1 hj.2.2) (lt_asymm hj.2.1)

lemma fcfs_Out {F : Sched I} (hF : IsFCFS F) (i : J) : F.Out i = 0 := by
  apply Finset.sum_eq_zero
  intro j hj
  rw [Finset.mem_filter] at hj
  exact absurd ((hF j i).1 hj.2.2) (lt_asymm hj.2.1)

lemma R_sub_R (P F : Sched I) (i : J) :
    P.R i - F.R i = P.U (I.a i) - F.U (I.a i) := by
  rw [P.U_at_arrival, F.U_at_arrival]
  ring

/-- Theorem "Net-overtake identity", the identity part. -/
theorem identity (P F : Sched I) (hF : IsFCFS F) (i : J) :
    Delta P F i = (P.R i - F.R i) - P.beta i + F.beta i := by
  have h1 := P.busy i
  have h2 := F.busy i
  rw [fcfs_In hF, fcfs_Out hF] at h2
  unfold Delta
  rw [mul_sub]
  linarith

/-- Theorem "Net-overtake identity", the bound `|Δ_i| ≤ 2(k-1)L`. -/
theorem identity_bound (P F : Sched I) (hF : IsFCFS F) (i : J) :
    |Delta P F i| ≤ 2 * ((I.k : ℝ) - 1) * I.L := by
  rw [identity P F hF i]
  have hR := workload_comparison P F (I.a i)
  rw [← R_sub_R] at hR
  have b1 := P.beta_nonneg i
  have b2 := P.beta_le i
  have b3 := F.beta_nonneg i
  have b4 := F.beta_le i
  rw [abs_le] at hR ⊢
  constructor <;> nlinarith [hR.1, hR.2]

/-- The equivalent form `|W_P[i] - W_FCFS[i] - (In_i - Out_i)/k| ≤ (2 - 2/k)L`. -/
theorem identity_bound' (P F : Sched I) (hF : IsFCFS F) (i : J) :
    |P.W i - F.W i - (P.In i - P.Out i) / I.k| ≤ (2 - 2 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hx : Delta P F i = (I.k : ℝ) * (P.W i - F.W i - (P.In i - P.Out i) / I.k) := by
    unfold Delta
    field_simp
  have hb := identity_bound P F hF i
  rw [hx, abs_mul, abs_of_pos hk] at hb
  have e : (2 - 2 / (I.k : ℝ)) * I.L = 2 * ((I.k : ℝ) - 1) * I.L / I.k := by
    field_simp
  rw [e, le_div_iff₀ hk]
  linarith

/-- At `k = 1`: `W_P[i] - W_FCFS[i] = In_i - Out_i` exactly. -/
theorem identity_k1 (hk : I.k = 1) (P F : Sched I) (hF : IsFCFS F) (i : J) :
    P.W i - F.W i = P.In i - P.Out i := by
  have hb := identity_bound P F hF i
  rw [hk, Nat.cast_one, sub_self, mul_zero, zero_mul] at hb
  have h0 : Delta P F i = 0 := abs_eq_zero.mp (le_antisymm hb (abs_nonneg _))
  unfold Delta at h0
  rw [hk, Nat.cast_one, one_mul] at h0
  linarith

/-- Theorem "Net-overtake identity", strict bound for `k ≥ 2`. -/
theorem identity_bound_strict (hk2 : 2 ≤ I.k) (P F : Sched I) (hF : IsFCFS F)
    (i : J) : |Delta P F i| < 2 * ((I.k : ℝ) - 1) * I.L := by
  rw [identity P F hF i]
  have hR := workload_comparison_strict hk2 P F (I.a i)
  rw [← R_sub_R] at hR
  have b1 := P.beta_nonneg i
  have b2 := P.beta_le i
  have b3 := F.beta_nonneg i
  have b4 := F.beta_le i
  rw [abs_lt] at hR ⊢
  constructor <;> nlinarith [hR.1, hR.2]

/-! ## Corollary "A work budget is sufficient" (06_theory.tex:174) -/

/-- Per job: `In_i - Out_i ≤ Z` implies `excess_P[i] ≤ Z/k + (2 - 2/k)L`. -/
theorem sufficient_job (P F : Sched I) (hF : IsFCFS F) (Z : ℝ) (i : J)
    (h : P.In i - P.Out i ≤ Z) :
    excess P F i ≤ Z / I.k + (2 - 2 / (I.k : ℝ)) * I.L := by
  have hk : (0 : ℝ) < I.k := by exact_mod_cast I.hk
  have hb := identity_bound P F hF i
  rw [abs_le] at hb
  unfold Delta at hb
  have e : Z / I.k + (2 - 2 / (I.k : ℝ)) * I.L = (Z + 2 * ((I.k : ℝ) - 1) * I.L) / I.k := by
    field_simp
  rw [e, le_div_iff₀ hk]
  unfold excess
  nlinarith [hb.2]

/-- Corollary "A work budget is sufficient", as stated: if `In_i - Out_i ≤ Z` for every
job, then `excess_P[i] ≤ Z/k + (2 - 2/k)L` for every job. -/
theorem sufficient (P F : Sched I) (hF : IsFCFS F) (Z : ℝ)
    (h : ∀ i, P.In i - P.Out i ≤ Z) :
    ∀ i, excess P F i ≤ Z / I.k + (2 - 2 / (I.k : ℝ)) * I.L :=
  fun i => sufficient_job P F hF Z i (h i)

lemma Out_nonneg (P : Sched I) (i : J) : 0 ≤ P.Out i :=
  sum_nonneg fun j _ => (I.hC_pos j).le

/-- The special case "in particular if it keeps `In_i ≤ Z`". -/
theorem sufficient_In (P F : Sched I) (hF : IsFCFS F) (Z : ℝ)
    (h : ∀ i, P.In i ≤ Z) :
    ∀ i, excess P F i ≤ Z / I.k + (2 - 2 / (I.k : ℝ)) * I.L :=
  sufficient P F hF Z fun i => by linarith [h i, Out_nonneg P i]

/-! ## Lemma "Outbound work under a guarantee" (06_theory.tex:218) -/

lemma vol_job (Q : Sched I) (j : J) :
    volume.real (Ico (Q.s j) (Q.s j + I.C j)) = I.C j := by
  simp [(I.hC_pos j).le]

theorem outbound (P F : Sched I) (hF : IsFCFS F) (G : ℝ) (i : J)
    (hi : excess P F i ≤ G)
    (hout : ∀ j, j < i → P.prec i j → excess P F j ≤ G) :
    P.Out i ≤ (I.k : ℝ) * (G - excess P F i + I.L) := by
  set w := G - excess P F i with hw_def
  have hwin : ∀ j, j < i → P.prec i j → P.s i ≤ P.s j ∧ P.s j ≤ P.s i + w := by
    intro j hj hp
    refine ⟨P.s_le_of_prec hp, ?_⟩
    have hFs : F.s j ≤ F.s i := F.s_le_of_prec ((hF i j).2 hj)
    have h1 := hout j hj hp
    simp only [hw_def, excess, Sched.W] at h1 ⊢
    linarith
  unfold Sched.Out
  rw [← Finset.sum_fiberwise _ P.srv]
  calc ∑ m, ∑ j ∈ (univ.filter (fun j => j < i ∧ P.prec i j)).filter
          (fun j => P.srv j = m), I.C j
      ≤ ∑ _m : Fin I.k, (w + I.L) := by
        apply sum_le_sum
        intro m _
        have := P.server_sum_le m (univ.filter (fun j => j < i ∧ P.prec i j))
          (fun j => Ico (P.s j) (P.s j + I.C j)) (fun j => subset_rfl)
          (fun j => measurableSet_Ico) (Ico (P.s i) (P.s i + w + I.L))
          measure_Ico_lt_top.ne (by
            intro j hj _
            rw [Finset.mem_filter] at hj
            have h := hwin j hj.2.1 hj.2.2
            apply Set.Ico_subset_Ico h.1
            linarith [I.hC_le j])
        have hwL : 0 ≤ w + I.L := by linarith [I.hL]
        simp only [vol_job] at this
        rw [Real.volume_real_Ico, max_eq_left (by linarith)] at this
        linarith
    _ = (I.k : ℝ) * (w + I.L) := by simp [mul_add]

/-! ## Corollary "A work budget is necessary" (06_theory.tex:236) -/

theorem necessary (P F : Sched I) (hF : IsFCFS F) (G : ℝ)
    (hG : ∀ j, excess P F j ≤ G) (i : J) :
    P.In i ≤ (I.k : ℝ) * G + (3 * (I.k : ℝ) - 2) * I.L := by
  have h1 := identity_bound P F hF i
  have h2 := outbound P F hF G i (hG i) fun j _ _ => hG j
  rw [abs_le] at h1
  unfold Delta at h1
  unfold excess at h2
  nlinarith [h1.1, h2]


/-! ## Theorem "Tightness" (06_theory.tex:189)

Witnesses for both directions, built on the cascade of Supplementary S8.1 with the
short work of a round cut into `k` pieces (one per server) instead of `L` unit jobs, and
an upward finale that differs from S8.2 (see `formal/REPORT.md`).  Notation: `K = k - 1`,
`c = K / (K + 1)`, `f r = L (1 - c^r)` is the remaining work that the carrying schedule
holds on each of `K` servers at the start of round `r`, round `r` occupies `[r L, (r+1) L)`.
-/

namespace Tight

/-! ### Lexicographic keys, encodings and time grids -/

def lexle (a b : ℕ × ℕ) : Prop := a.1 < b.1 ∨ (a.1 = b.1 ∧ a.2 ≤ b.2)
def lexlt (a b : ℕ × ℕ) : Prop := a.1 < b.1 ∨ (a.1 = b.1 ∧ a.2 < b.2)

lemma lexle_of_not_lexlt {a b : ℕ × ℕ} (h : ¬ lexlt a b) : lexle b a := by
  unfold lexlt at h
  unfold lexle
  omega

/-- `G (r, p) = r L + ofs r p`. -/
def grid (L : ℝ) (ofs : ℕ → ℕ → ℝ) (a : ℕ × ℕ) : ℝ := (a.1 : ℝ) * L + ofs a.1 a.2

structure GoodOfs (L : ℝ) (ofs : ℕ → ℕ → ℝ) : Prop where
  nonneg : ∀ r p, 0 ≤ ofs r p
  le : ∀ r p, ofs r p ≤ L
  mono : ∀ r p q, p ≤ q → ofs r p ≤ ofs r q

lemma grid_mono {L : ℝ} {ofs : ℕ → ℕ → ℝ} (h : GoodOfs L ofs) {a b : ℕ × ℕ}
    (hab : lexle a b) : grid L ofs a ≤ grid L ofs b := by
  unfold grid
  rcases hab with hlt | ⟨h1, h2⟩
  · have h' : (a.1 : ℝ) + 1 ≤ b.1 := by exact_mod_cast hlt
    have hL0 : 0 ≤ L := (h.nonneg 0 0).trans (h.le 0 0)
    have e1 := h.nonneg b.1 b.2
    have e2 := h.le a.1 a.2
    nlinarith
  · rw [h1]
    linarith [h.mono b.1 a.2 b.2 h2]

def enc (N : ℕ) (a : ℕ × ℕ) : ℕ := a.1 * N + a.2

lemma mul_add_lt_iff {N x y u v : ℕ} (hu : u < N) (hv : v < N) :
    x * N + u < y * N + v ↔ x < y ∨ (x = y ∧ u < v) := by
  constructor
  · intro h
    by_contra hc
    push Not at hc
    rcases Nat.lt_or_ge y x with hyx | hyx
    · have := Nat.mul_le_mul_right N (Nat.succ_le_of_lt hyx)
      rw [Nat.succ_mul] at this
      omega
    · have hxy : x = y := by omega
      have := hc.2 hxy
      subst hxy
      omega
  · rintro (h | ⟨rfl, h⟩)
    · have := Nat.mul_le_mul_right N (Nat.succ_le_of_lt h)
      rw [Nat.succ_mul] at this
      omega
    · omega

lemma mul_add_inj {N x y u v : ℕ} (hu : u < N) (hv : v < N)
    (h : x * N + u = y * N + v) : x = y ∧ u = v := by
  have h1 := (mul_add_lt_iff (x := x) (y := y) hu hv).not.mp (by omega)
  have h2 := (mul_add_lt_iff (x := y) (y := x) hv hu).not.mp (by omega)
  push Not at h1 h2
  omega

lemma enc_lt_iff {N : ℕ} {a b : ℕ × ℕ} (ha : a.2 < N) (hb : b.2 < N) :
    enc N a < enc N b ↔ lexlt a b := mul_add_lt_iff ha hb

lemma enc_inj {N : ℕ} {a b : ℕ × ℕ} (ha : a.2 < N) (hb : b.2 < N)
    (h : enc N a = enc N b) : a = b := by
  obtain ⟨h1, h2⟩ := mul_add_inj ha hb h
  exact Prod.ext h1 h2

/-- Two-level encoding: a lexicographic key, then an index breaking ties. -/
def enc2 (N : ℕ) (a : ℕ × ℕ) (i : ℕ) : ℕ := enc N a * N + i

lemma enc2_lt_iff {N : ℕ} {a b : ℕ × ℕ} {i j : ℕ} (ha : a.2 < N) (hb : b.2 < N)
    (hi : i < N) (hj : j < N) :
    enc2 N a i < enc2 N b j ↔ lexlt a b ∨ (a = b ∧ i < j) := by
  unfold enc2
  rw [mul_add_lt_iff hi hj, enc_lt_iff ha hb]
  constructor
  · rintro (h | ⟨h1, h2⟩)
    · exact Or.inl h
    · exact Or.inr ⟨enc_inj ha hb h1, h2⟩
  · rintro (h | ⟨rfl, h2⟩)
    · exact Or.inl h
    · exact Or.inr ⟨rfl, h2⟩

lemma enc2_inj {N : ℕ} {a b : ℕ × ℕ} {i j : ℕ} (ha : a.2 < N) (hb : b.2 < N)
    (hi : i < N) (hj : j < N) (h : enc2 N a i = enc2 N b j) : a = b ∧ i = j := by
  obtain ⟨h1, h2⟩ := mul_add_inj hi hj h
  exact ⟨enc_inj ha hb h1, h2⟩

/-! ### The cascade sequence -/

section Seq

variable (K : ℕ) (L : ℝ)

def cc : ℝ := (K : ℝ) / (K + 1)
def ff (r : ℕ) : ℝ := L * (1 - cc K ^ r)
def dd (r : ℕ) : ℝ := ff K L (r + 1) - ff K L r

variable {K L}

lemma cc_pos (hK : 1 ≤ K) : 0 < cc K := by
  unfold cc
  have : (1 : ℝ) ≤ K := by exact_mod_cast hK
  positivity

lemma cc_lt_one : cc K < 1 := by
  unfold cc
  rw [div_lt_one (by positivity)]
  linarith

lemma cc_nonneg : 0 ≤ cc K := by
  unfold cc
  positivity

lemma ff_zero : ff K L 0 = 0 := by simp [ff]

lemma ff_lt (hL : 0 < L) (hK : 1 ≤ K) (r : ℕ) : ff K L r < L := by
  unfold ff
  have := pow_pos (cc_pos hK) r
  nlinarith

lemma ff_le (hL : 0 < L) (hK : 1 ≤ K) (r : ℕ) : ff K L r ≤ L := (ff_lt hL hK r).le

lemma ff_nonneg (hL : 0 < L) (r : ℕ) : 0 ≤ ff K L r := by
  unfold ff
  have := pow_le_one₀ (cc_nonneg (K := K)) cc_lt_one.le (n := r)
  nlinarith

lemma ff_mono (hL : 0 < L) {r r' : ℕ} (h : r ≤ r') : ff K L r ≤ ff K L r' := by
  unfold ff
  have := pow_le_pow_of_le_one (cc_nonneg (K := K)) cc_lt_one.le h
  nlinarith

lemma dd_pos (hL : 0 < L) (hK : 1 ≤ K) (r : ℕ) : 0 < dd K L r := by
  unfold dd ff
  have h1 := pow_pos (cc_pos hK) r
  have h2 : cc K ^ (r + 1) < cc K ^ r := by
    rw [pow_succ]
    have := cc_lt_one (K := K)
    nlinarith
  nlinarith

lemma ff_succ_pos (hL : 0 < L) (hK : 1 ≤ K) (r : ℕ) : 0 < ff K L (r + 1) := by
  have := dd_pos hL hK r
  have := ff_nonneg (K := K) hL r
  unfold dd at *
  linarith

/-- `f (r+1) + K (f (r+1) - f r) = L`: the short work of a round fills one server. -/
lemma ff_fill (r : ℕ) : ff K L (r + 1) + K * dd K L r = L := by
  unfold dd ff cc
  rw [pow_succ]
  field_simp
  ring

lemma ff_tendsto (hL : 0 < L) (hK : 1 ≤ K) {ε : ℝ} (hε : 0 < ε) :
    ∃ m : ℕ, 1 ≤ m ∧ (K : ℝ) * L * cc K ^ m < ε := by
  have hKL : 0 < (K : ℝ) * L := by
    have : (1 : ℝ) ≤ K := by exact_mod_cast hK
    positivity
  obtain ⟨n, hn⟩ := exists_pow_lt_of_lt_one (div_pos hε hKL) (cc_lt_one (K := K))
  refine ⟨n + 1, by omega, ?_⟩
  have h1 : cc K ^ (n + 1) ≤ cc K ^ n :=
    pow_le_pow_of_le_one cc_nonneg cc_lt_one.le (by omega)
  rw [lt_div_iff₀ hKL] at hn
  nlinarith

end Seq

end Tight


namespace Tight

/-! ### Building a schedule from a time grid -/

/-- A schedule whose start times are grid points `G (key j)`, whose dispatch order
respects the lexicographic order of the keys, and whose jobs end at grid points `hi j`
that do not cross on one server. -/
def mkSched {J : Type} [Fintype J] [LinearOrder J] (I : Input J)
    (L : ℝ) (ofs : ℕ → ℕ → ℝ) (hofs : GoodOfs L ofs) (key hi : J → ℕ × ℕ)
    (srv : J → Fin I.k) (ord : J → ℕ)
    (hord_inj : Function.Injective ord)
    (hord : ∀ i j, lexlt (key j) (key i) → ord j < ord i)
    (hstart : ∀ j, I.a j ≤ grid L ofs (key j))
    (hhi : ∀ j, grid L ofs (key j) + I.C j ≤ grid L ofs (hi j))
    (hpair : ∀ i j, i ≠ j → srv i = srv j → lexle (hi i) (key j) ∨ lexle (hi j) (key i))
    (hwc : ∀ t, (∃ i, I.a i ≤ t ∧ t < grid L ofs (key i)) → ∀ σ, ∃ j, srv j = σ ∧
      grid L ofs (key j) ≤ t ∧ t < grid L ofs (key j) + I.C j) : Sched I where
  s := fun j => grid L ofs (key j)
  srv := srv
  ord := ord
  start_ge := hstart
  ord_inj := hord_inj
  ord_refines := by
    intro i j h
    apply hord
    by_contra hc
    exact absurd h (not_lt.mpr (grid_mono hofs (lexle_of_not_lexlt hc)))
  no_overlap := by
    intro i j hij hs
    rcases hpair i j hij hs with h | h
    · left
      exact (hhi i).trans (grid_mono hofs h)
    · right
      exact (hhi j).trans (grid_mono hofs h)
  work_conserving := hwc

/-! ### The two offset tables -/

/-- Flat shape: in round `r < m` the long jobs and one short job start at `r L`, the
pieces follow one another on the last server from `r L + f (r+1)`. -/
def ofsFlat (m K : ℕ) (L : ℝ) (r p : ℕ) : ℝ :=
  if p = 0 ∨ m ≤ r then 0 else min (ff K L (r + 1) + ((p - 1 : ℕ) : ℝ) * dd K L r) L

/-- Carrying shape: in round `r` the short job starts at `r L`, the pieces at
`r L + f r` (when the carried long jobs finish), the long jobs at `r L + f (r+1)`. -/
def ofsCarry (m K : ℕ) (L : ℝ) (r p : ℕ) : ℝ :=
  if p = 0 then 0 else if p = 1 then ff K L (min r m) else ff K L (r + 1)

lemma good_flat {m K : ℕ} {L : ℝ} (hL : 0 < L) (hK : 1 ≤ K) : GoodOfs L (ofsFlat m K L) where
  nonneg r p := by
    unfold ofsFlat
    split_ifs
    · exact le_rfl
    · have := ff_nonneg (K := K) hL (r + 1)
      have := (dd_pos hL hK r).le
      exact le_min (by positivity) hL.le
  le r p := by
    unfold ofsFlat
    split_ifs
    · exact hL.le
    · exact min_le_right _ _
  mono r p q hpq := by
    unfold ofsFlat
    split_ifs with h1 h2
    · exact le_rfl
    · have := ff_nonneg (K := K) hL (r + 1)
      have := (dd_pos hL hK r).le
      exact le_min (by positivity) hL.le
    · omega
    · apply min_le_min_right
      have : ((p - 1 : ℕ) : ℝ) ≤ ((q - 1 : ℕ) : ℝ) := by exact_mod_cast Nat.sub_le_sub_right hpq 1
      have := (dd_pos hL hK r).le
      nlinarith

lemma good_carry {m K : ℕ} {L : ℝ} (hL : 0 < L) (hK : 1 ≤ K) :
    GoodOfs L (ofsCarry m K L) where
  nonneg r p := by
    unfold ofsCarry
    split_ifs
    · exact le_rfl
    · exact ff_nonneg hL _
    · exact ff_nonneg hL _
  le r p := by
    unfold ofsCarry
    split_ifs
    · exact hL.le
    · exact ff_le hL hK _
    · exact ff_le hL hK _
  mono r p q hpq := by
    unfold ofsCarry
    split_ifs <;> first
      | exact le_rfl
      | exact ff_nonneg hL _
      | omega
      | exact ff_mono hL (by omega)

lemma flat_piece_le {K : ℕ} {L : ℝ} (hL : 0 < L) (hK : 1 ≤ K) (r q : ℕ) (hq : q ≤ K) :
    ff K L (r + 1) + (q : ℝ) * dd K L r ≤ L := by
  have h1 := ff_fill (K := K) (L := L) r
  have h2 := (dd_pos hL hK r).le
  have : (q : ℝ) ≤ K := by exact_mod_cast hq
  nlinarith

lemma ofsFlat_piece {m K : ℕ} {L : ℝ} (hL : 0 < L) (hK : 1 ≤ K) {r q : ℕ} (hr : r < m)
    (hq : q ≤ K) : ofsFlat m K L r (q + 1) = ff K L (r + 1) + (q : ℝ) * dd K L r := by
  unfold ofsFlat
  rw [if_neg (by omega), Nat.add_sub_cancel, min_eq_left (flat_piece_le hL hK r q hq)]

lemma ofsFlat_zero {m K : ℕ} {L : ℝ} (r : ℕ) : ofsFlat m K L r 0 = 0 := by
  simp [ofsFlat]

lemma ofsFlat_late {m K : ℕ} {L : ℝ} {r : ℕ} (hr : m ≤ r) (p : ℕ) : ofsFlat m K L r p = 0 := by
  simp [ofsFlat, hr]

lemma ofsCarry_zero {m K : ℕ} {L : ℝ} (r : ℕ) : ofsCarry m K L r 0 = 0 := by
  simp [ofsCarry]

lemma ofsCarry_one {m K : ℕ} {L : ℝ} (r : ℕ) : ofsCarry m K L r 1 = ff K L (min r m) := by
  simp [ofsCarry]

lemma ofsCarry_two {m K : ℕ} {L : ℝ} (r : ℕ) : ofsCarry m K L r 2 = ff K L (r + 1) := by
  simp [ofsCarry]

/-- Locating a time inside a run of consecutive pieces of length `d`. -/
lemma find_piece {K : ℕ} {d B t : ℝ} (hd : 0 < d) (h1 : B ≤ t) (h2 : t < B + K * d) :
    ∃ q : ℕ, q < K ∧ B + q * d ≤ t ∧ t < B + q * d + d := by
  set x := (t - B) / d with hx
  have hx0 : 0 ≤ x := div_nonneg (by linarith) hd.le
  refine ⟨⌊x⌋₊, ?_, ?_, ?_⟩
  · rw [Nat.floor_lt hx0, hx, div_lt_iff₀ hd]
    linarith
  · have := Nat.floor_le hx0
    have e : x * d = t - B := by rw [hx]; field_simp
    nlinarith
  · have := Nat.lt_floor_add_one x
    have e : x * d = t - B := by rw [hx]; field_simp
    nlinarith

/-! ### Upward witness -/

/-- Jobs of the upward witness: `m` cascade rounds (`K` long jobs, one short job and `K`
pieces each), then `K` new long jobs, the victim and two overtakers `g1`, `g2`.
The constructor order is not the rank; the rank is `UJ.rank`. -/
inductive UJ (m K : ℕ) where
  | long (r : Fin m) (q : Fin K)
  | short0 (r : Fin m)
  | piece (r : Fin m) (q : Fin K)
  | newlong (q : Fin K)
  | victim
  | g1
  | g2
  deriving DecidableEq, Fintype

namespace UJ

variable {m K : ℕ}

/-- FCFS key (round, phase); together with `idx` it is the rank. -/
def key : UJ m K → ℕ × ℕ
  | long r _ => (r, 0)
  | short0 r => (r, 0)
  | piece r q => (r, q + 1)
  | newlong _ => (m, 0)
  | victim => (m, 0)
  | g1 => (m + 1, 0)
  | g2 => (m + 1, 0)

def idx : UJ m K → ℕ
  | long _ q => q
  | short0 _ => K
  | piece _ _ => 0
  | newlong q => q
  | victim => K
  | g1 => 0
  | g2 => 1

lemma key_snd_lt (j : UJ m K) : (key j).2 < K + 2 := by
  cases j <;> simp [key] <;> omega

lemma idx_lt (j : UJ m K) : idx j < K + 2 := by
  cases j <;> simp [idx] <;> omega

/-- Rank (arrival order): round by round, in each round the long jobs, the short job,
then the pieces; then the new long jobs, the victim, `g1`, `g2`. -/
def rank (j : UJ m K) : ℕ := enc2 (K + 2) (key j) (idx j)

lemma rank_lt_iff (i j : UJ m K) :
    rank i < rank j ↔ lexlt (key i) (key j) ∨ (key i = key j ∧ idx i < idx j) :=
  enc2_lt_iff (key_snd_lt i) (key_snd_lt j) (idx_lt i) (idx_lt j)

lemma rank_inj : Function.Injective (@rank m K) := by
  intro a b h
  obtain ⟨h1, h2⟩ := enc2_inj (key_snd_lt a) (key_snd_lt b) (idx_lt a) (idx_lt b) h
  cases a <;> cases b <;> simp [key, idx, Prod.ext_iff, Fin.ext_iff] at h1 h2 ⊢ <;> omega

instance : LinearOrder (UJ m K) := LinearOrder.lift' rank rank_inj

lemma lt_iff (i j : UJ m K) : i < j ↔ rank i < rank j := Iff.rfl

variable (m K) in
def arr (L : ℝ) (j : UJ m K) : ℝ := ((min (key j).1 m : ℕ) : ℝ) * L

variable (m K) in
def cost (L : ℝ) : UJ m K → ℝ
  | long _ _ => L
  | short0 r => ff K L (r + 1)
  | piece r _ => dd K L r
  | newlong _ => L
  | victim => L
  | g1 => L
  | g2 => ff K L m

lemma min_fin (r : Fin m) : min (r : ℕ) m = r := min_eq_left r.isLt.le

def input (m K : ℕ) (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m) : Input (UJ m K) where
  k := K + 1
  L := L
  a := arr m K L
  C := cost m K L
  hk := by omega
  hL := hL
  ha_nonneg j := by unfold arr; positivity
  ha_mono := by
    intro i j hij
    have h1 : (key i).1 ≤ (key j).1 := by
      have : ¬ rank j < rank i := not_lt.mpr hij
      rw [rank_lt_iff] at this
      unfold lexlt at this
      omega
    have : ((min (key i).1 m : ℕ) : ℝ) ≤ (min (key j).1 m : ℕ) := by
      exact_mod_cast min_le_min_right m h1
    exact mul_le_mul_of_nonneg_right this hL.le
  hC_pos j := by
    cases j with
    | long => exact hL
    | short0 r => exact ff_succ_pos hL hK r
    | piece r => exact dd_pos hL hK r
    | newlong => exact hL
    | victim => exact hL
    | g1 => exact hL
    | g2 =>
      obtain ⟨m', rfl⟩ : ∃ m', m = m' + 1 := ⟨m - 1, by omega⟩
      exact ff_succ_pos hL hK m'
  hC_le j := by
    cases j with
    | long => exact le_rfl
    | short0 r => exact ff_le hL hK _
    | piece r =>
      show dd K L r ≤ L
      unfold dd
      linarith [ff_nonneg (K := K) hL r, ff_le (K := K) hL hK (r + 1)]
    | newlong => exact le_rfl
    | victim => exact le_rfl
    | g1 => exact le_rfl
    | g2 => exact ff_le hL hK _

/-! #### The FCFS schedule (flat) -/

def srvF [NeZero K] : UJ m K → Fin (K + 1)
  | long _ q => q.castSucc
  | short0 _ => Fin.last K
  | piece _ _ => Fin.last K
  | newlong q => q.castSucc
  | victim => Fin.last K
  | g1 => Fin.last K
  | g2 => (0 : Fin K).castSucc

def hiF : UJ m K → ℕ × ℕ
  | long r _ => (r + 1, 0)
  | short0 r => (r, 1)
  | piece r q => (r, q + 2)
  | newlong _ => (m + 1, 0)
  | victim => (m + 1, 0)
  | g1 => (m + 2, 0)
  | g2 => (m + 2, 0)

section F

variable {L : ℝ} (hL : 0 < L) (hK : 1 ≤ K)
include hL hK

lemma sF_piece (r : Fin m) (q : Fin K) :
    grid L (ofsFlat m K L) (key (piece r q)) = r * L + ff K L (r + 1) + q * dd K L r := by
  simp only [grid, key]
  rw [ofsFlat_piece hL hK r.isLt q.isLt.le]
  ring

lemma flat_busy [NeZero K] (r : Fin m) {t : ℝ} (h1 : (r : ℝ) * L ≤ t) (h2 : t < r * L + L)
    (σ : Fin (K + 1)) : ∃ j : UJ m K, srvF j = σ ∧ grid L (ofsFlat m K L) (key j) ≤ t ∧
      t < grid L (ofsFlat m K L) (key j) + cost m K L j := by
  induction σ using Fin.lastCases with
  | last =>
    by_cases h3 : t < r * L + ff K L (r + 1)
    · exact ⟨short0 r, rfl, by simp [grid, key, ofsFlat_zero]; linarith,
        by simp [grid, key, ofsFlat_zero, cost]; linarith⟩
    · push Not at h3
      have hfill := ff_fill (K := K) (L := L) r
      obtain ⟨q, hq, hq1, hq2⟩ := find_piece (K := K) (dd_pos hL hK r) h3 (by linarith)
      refine ⟨piece r ⟨q, hq⟩, rfl, ?_, ?_⟩
      · rw [sF_piece hL hK]
        exact hq1
      · rw [sF_piece hL hK]
        exact hq2
  | cast q =>
    exact ⟨long r q, rfl, by simp [grid, key, ofsFlat_zero]; linarith,
      by simp [grid, key, ofsFlat_zero, cost]; linarith⟩

lemma flat_busy_final [NeZero K] {t : ℝ} (h1 : (m : ℝ) * L ≤ t) (h2 : t < m * L + L)
    (σ : Fin (K + 1)) : ∃ j : UJ m K, srvF j = σ ∧ grid L (ofsFlat m K L) (key j) ≤ t ∧
      t < grid L (ofsFlat m K L) (key j) + cost m K L j := by
  induction σ using Fin.lastCases with
  | last =>
    exact ⟨victim, rfl, by simp [grid, key, ofsFlat_zero]; linarith,
      by simp [grid, key, ofsFlat_zero, cost]; linarith⟩
  | cast q =>
    exact ⟨newlong q, rfl, by simp [grid, key, ofsFlat_zero]; linarith,
      by simp [grid, key, ofsFlat_zero, cost]; linarith⟩

end F

lemma pairF [NeZero K] (i j : UJ m K) (hij : i ≠ j) (hs : srvF i = srvF j) :
    lexle (hiF i) (key j) ∨ lexle (hiF j) (key i) := by
  have hK0 : K ≠ 0 := NeZero.ne K
  cases i <;> cases j <;> simp only [srvF, hiF, key, lexle, Fin.ext_iff, Fin.val_last, Fin.val_castSucc, ne_eq, reduceCtorEq, not_false_eq_true, not_true_eq_false, eq_self_iff_true, UJ.long.injEq, UJ.short0.injEq, UJ.piece.injEq, UJ.newlong.injEq, Fin.val_zero] at hij hs ⊢ <;>
    (try simp only [true_and, and_true, true_or, or_true, le_refl] at hij hs ⊢) <;> omega

def schedF (m K : ℕ) [NeZero K] (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m) :
    Sched (input m K L hL hK hm) :=
  mkSched (input m K L hL hK hm) L (ofsFlat m K L) (good_flat hL hK) key hiF srvF rank
    rank_inj
    (fun i j h => (rank_lt_iff j i).mpr (Or.inl h))
    (by
      intro j
      show arr m K L j ≤ grid L (ofsFlat m K L) (key j)
      unfold arr grid
      have h1 : ((min (key j).1 m : ℕ) : ℝ) ≤ (key j).1 := by exact_mod_cast min_le_left _ _
      have := (good_flat (m := m) hL hK).nonneg (key j).1 (key j).2
      nlinarith)
    (by
      intro j
      show grid L (ofsFlat m K L) (key j) + cost m K L j ≤ grid L (ofsFlat m K L) (hiF j)
      cases j with
      | long r q => simp [grid, key, hiF, ofsFlat_zero, cost]; linarith
      | short0 r =>
        simp only [grid, key, hiF, ofsFlat_zero, cost]
        rw [show (1 : ℕ) = 0 + 1 from rfl, ofsFlat_piece hL hK r.isLt (Nat.zero_le _)]
        simp
      | piece r q =>
        simp only [grid, key, hiF, cost]
        rw [ofsFlat_piece hL hK r.isLt q.isLt.le,
          show (q : ℕ) + 2 = ((q : ℕ) + 1) + 1 by ring,
          ofsFlat_piece hL hK r.isLt (by omega)]
        push_cast
        ring_nf
        rfl
      | newlong q => simp [grid, key, hiF, ofsFlat_zero, cost]; linarith
      | victim => simp [grid, key, hiF, ofsFlat_zero, cost]; linarith
      | g1 => simp [grid, key, hiF, ofsFlat_zero, cost]; linarith
      | g2 =>
        simp [grid, key, hiF, ofsFlat_zero, cost]
        linarith [ff_le (K := K) hL hK m])
    (fun i j hij hs => pairF i j hij hs)
    (by
      rintro t ⟨i, hai, hti⟩ σ
      change arr m K L i ≤ t at hai
      cases i with
      | long r q => simp [arr, grid, key, ofsFlat_zero, min_fin] at hai hti; linarith
      | short0 r => simp [arr, grid, key, ofsFlat_zero, min_fin] at hai hti; linarith
      | piece r q =>
        simp only [arr, key, min_fin] at hai
        rw [sF_piece hL hK] at hti
        have := flat_piece_le hL hK r q q.isLt.le
        have := dd_pos hL hK r
        have hq : (q : ℝ) * dd K L r + dd K L r ≤ K * dd K L r := by
          have : (q : ℝ) + 1 ≤ K := by exact_mod_cast q.isLt
          nlinarith
        have := ff_fill (K := K) (L := L) r
        exact flat_busy hL hK r hai (by linarith) σ
      | newlong q => simp [arr, grid, key, ofsFlat_zero] at hai hti; linarith
      | victim => simp [arr, grid, key, ofsFlat_zero] at hai hti; linarith
      | g1 =>
        simp [arr, grid, key, ofsFlat_zero] at hai hti
        exact flat_busy_final hL hK hai (by push_cast at hti; linarith) σ
      | g2 =>
        simp [arr, grid, key, ofsFlat_zero] at hai hti
        exact flat_busy_final hL hK hai (by push_cast at hti; linarith) σ)

lemma schedF_fcfs (m K : ℕ) [NeZero K] (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m) :
    IsFCFS (schedF m K L hL hK hm) := fun _ _ => Iff.rfl

end UJ

end Tight


namespace Tight

namespace UJ

variable {m K : ℕ}

/-! #### The base policy `P` (carrying) -/

/-- Key (round, phase) of the start under `P`. -/
def keyP : UJ m K → ℕ × ℕ
  | short0 r => (r, 0)
  | piece r _ => (r, 1)
  | long r _ => (r, 2)
  | g1 => (m, 0)
  | newlong _ => (m, 1)
  | g2 => (m + 1, 0)
  | victim => (m + 1, 1)

def hiP : UJ m K → ℕ × ℕ
  | short0 r => (r, 2)
  | piece r _ => (r, 2)
  | long r _ => (r + 1, 1)
  | g1 => (m + 1, 0)
  | newlong _ => (m + 1, 1)
  | g2 => (m + 1, 1)
  | victim => (m + 2, 1)

def srvP [NeZero K] : UJ m K → Fin (K + 1)
  | short0 _ => Fin.last K
  | piece _ q => q.castSucc
  | long _ q => q.castSucc
  | g1 => Fin.last K
  | newlong q => q.castSucc
  | g2 => Fin.last K
  | victim => Fin.last K

lemma keyP_snd_lt (hK : 1 ≤ K) (j : UJ m K) : (keyP j).2 < K + 2 := by
  cases j <;> simp [keyP] <;> omega

variable (m K) in
def big : ℕ := enc2 (K + 2) (m + 2, 0) 0

lemma rank_lt_big (j : UJ m K) : rank j < big m K := by
  unfold big rank
  rw [enc2_lt_iff (key_snd_lt j) (by simp) (idx_lt j) (by omega)]
  left
  cases j <;> simp [key, lexlt] <;> omega

def ordP (j : UJ m K) : ℕ := enc (big m K) (enc (K + 2) (keyP j), rank j)

lemma ordP_lt_iff (hK : 1 ≤ K) (i j : UJ m K) :
    ordP i < ordP j ↔ lexlt (keyP i) (keyP j) ∨ (keyP i = keyP j ∧ rank i < rank j) := by
  unfold ordP enc
  rw [mul_add_lt_iff (rank_lt_big i) (rank_lt_big j)]
  change enc (K + 2) (keyP i) < enc (K + 2) (keyP j) ∨ _ ↔ _
  rw [enc_lt_iff (keyP_snd_lt hK i) (keyP_snd_lt hK j)]
  constructor
  · rintro (h | ⟨h1, h2⟩)
    · exact Or.inl h
    · exact Or.inr ⟨enc_inj (keyP_snd_lt hK i) (keyP_snd_lt hK j) h1, h2⟩
  · rintro (h | ⟨h1, h2⟩)
    · exact Or.inl h
    · exact Or.inr ⟨by rw [h1], h2⟩

lemma ordP_inj : Function.Injective (@ordP m K) := by
  intro a b h
  exact rank_inj (mul_add_inj (rank_lt_big a) (rank_lt_big b) h).2

lemma pairP [NeZero K] (i j : UJ m K) (hij : i ≠ j) (hs : srvP i = srvP j) :
    lexle (hiP i) (keyP j) ∨ lexle (hiP j) (keyP i) := by
  have hK0 : K ≠ 0 := NeZero.ne K
  cases i <;> cases j <;> simp only [srvP, hiP, keyP, lexle, Fin.ext_iff, Fin.val_last,
    Fin.val_castSucc, ne_eq, reduceCtorEq, not_false_eq_true, not_true_eq_false, eq_self_iff_true,
    UJ.long.injEq, UJ.short0.injEq, UJ.piece.injEq, UJ.newlong.injEq, Fin.val_zero]
    at hij hs ⊢ <;>
    (try simp only [true_and, and_true, true_or, or_true, le_refl] at hij hs ⊢) <;> omega

section P

variable {L : ℝ} (hL : 0 < L) (hK : 1 ≤ K)
include hL hK

lemma carry_busy [NeZero K] (r : Fin m) {t : ℝ} (h1 : (r : ℝ) * L ≤ t)
    (h2 : t < r * L + ff K L (r + 1)) (σ : Fin (K + 1)) :
    ∃ j : UJ m K, srvP j = σ ∧ grid L (ofsCarry m K L) (keyP j) ≤ t ∧
      t < grid L (ofsCarry m K L) (keyP j) + cost m K L j := by
  induction σ using Fin.lastCases with
  | last =>
    exact ⟨short0 r, rfl, by simp [grid, keyP, ofsCarry_zero]; linarith,
      by simp [grid, keyP, ofsCarry_zero, cost]; linarith⟩
  | cast q =>
    by_cases h3 : t < r * L + ff K L r
    · obtain ⟨r', hr'⟩ : ∃ r' : ℕ, (r : ℕ) = r' + 1 := by
        rcases Nat.eq_zero_or_pos (r : ℕ) with h0 | h0
        · rw [h0, ff_zero] at h3
          simp [h0] at h1 h3
          linarith
        · exact ⟨(r : ℕ) - 1, by omega⟩
      have hfL := ff_le (K := K) hL hK (r' + 1)
      refine ⟨long ⟨r', by omega⟩ q, rfl, ?_, ?_⟩
      · simp only [grid, keyP, ofsCarry_two]
        rw [hr'] at h1
        push_cast at h1
        linarith
      · simp only [grid, keyP, ofsCarry_two, cost]
        rw [hr'] at h3
        push_cast at h3
        linarith
    · push Not at h3
      refine ⟨piece r q, rfl, ?_, ?_⟩
      · simp only [grid, keyP, ofsCarry_one, min_fin]
        exact h3
      · simp only [grid, keyP, ofsCarry_one, min_fin, cost, dd]
        linarith

lemma carry_busy_final [NeZero K] (hm : 1 ≤ m) {t : ℝ} (h1 : (m : ℝ) * L ≤ t)
    (h2 : t < (m + 1) * L + ff K L m) (σ : Fin (K + 1)) :
    ∃ j : UJ m K, srvP j = σ ∧ grid L (ofsCarry m K L) (keyP j) ≤ t ∧
      t < grid L (ofsCarry m K L) (keyP j) + cost m K L j := by
  induction σ using Fin.lastCases with
  | last =>
    by_cases h3 : t < m * L + L
    · exact ⟨g1, rfl, by simp [grid, keyP, ofsCarry_zero]; linarith,
        by simp [grid, keyP, ofsCarry_zero, cost]; linarith⟩
    · push Not at h3
      refine ⟨g2, rfl, ?_, ?_⟩
      · simp [grid, keyP, ofsCarry_zero]
        linarith
      · simp [grid, keyP, ofsCarry_zero, cost]
        linarith
  | cast q =>
    by_cases h3 : t < m * L + ff K L m
    · obtain ⟨m', rfl⟩ : ∃ m' : ℕ, m = m' + 1 := ⟨m - 1, by omega⟩
      have hfL := ff_le (K := K) hL hK (m' + 1)
      refine ⟨long ⟨m', by omega⟩ q, rfl, ?_, ?_⟩
      · simp only [grid, keyP, ofsCarry_two]
        push_cast at h1 ⊢
        linarith
      · simp only [grid, keyP, ofsCarry_two, cost]
        push_cast at h3 ⊢
        linarith
    · push Not at h3
      have hfL := ff_le (K := K) hL hK m
      refine ⟨newlong q, rfl, ?_, ?_⟩
      · simp only [grid, keyP, ofsCarry_one, min_self]
        exact h3
      · simp only [grid, keyP, ofsCarry_one, min_self, cost]
        linarith

end P

def schedP (m K : ℕ) [NeZero K] (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m) :
    Sched (input m K L hL hK hm) :=
  mkSched (input m K L hL hK hm) L (ofsCarry m K L) (good_carry hL hK) keyP hiP srvP ordP
    ordP_inj
    (fun i j h => (ordP_lt_iff hK j i).mpr (Or.inl h))
    (by
      intro j
      show arr m K L j ≤ grid L (ofsCarry m K L) (keyP j)
      unfold arr grid
      have h0 : min (key j).1 m ≤ (keyP j).1 := by
        cases j <;> simp [key, keyP] <;> omega
      have h1 : ((min (key j).1 m : ℕ) : ℝ) ≤ (keyP j).1 := by exact_mod_cast h0
      have := (good_carry (m := m) hL hK).nonneg (keyP j).1 (keyP j).2
      nlinarith)
    (by
      intro j
      show grid L (ofsCarry m K L) (keyP j) + cost m K L j ≤ grid L (ofsCarry m K L) (hiP j)
      have hfL := ff_le (K := K) hL hK m
      cases j with
      | short0 r => simp [grid, keyP, hiP, ofsCarry_zero, ofsCarry_two, cost]
      | piece r q => simp [grid, keyP, hiP, ofsCarry_one, ofsCarry_two, min_fin, cost, dd]
      | long r q =>
        simp only [grid, keyP, hiP, ofsCarry_one, ofsCarry_two, cost]
        rw [min_eq_left (by omega : (r : ℕ) + 1 ≤ m)]
        push_cast
        linarith
      | g1 => simp [grid, keyP, hiP, ofsCarry_zero, cost]; linarith
      | newlong q => simp [grid, keyP, hiP, ofsCarry_one, cost]; linarith
      | g2 => simp [grid, keyP, hiP, ofsCarry_zero, ofsCarry_one, cost]
      | victim =>
        simp only [grid, keyP, hiP, ofsCarry_one, cost]
        rw [min_eq_right (by omega : m ≤ m + 1), min_eq_right (by omega : m ≤ m + 2)]
        push_cast
        linarith)
    (fun i j hij hs => pairP i j hij hs)
    (by
      rintro t ⟨i, hai, hti⟩ σ
      change arr m K L i ≤ t at hai
      have hfL := ff_le (K := K) hL hK m
      cases i with
      | short0 r => simp [arr, grid, keyP, ofsCarry_zero, key] at hai hti; linarith
      | piece r q =>
        simp only [arr, key, min_fin] at hai
        simp only [grid, keyP, ofsCarry_one, min_fin] at hti
        have := ff_mono (K := K) hL (Nat.le_succ (r : ℕ))
        exact carry_busy hL hK r hai (by linarith) σ
      | long r q =>
        simp only [arr, key, min_fin] at hai
        simp only [grid, keyP, ofsCarry_two] at hti
        exact carry_busy hL hK r hai hti σ
      | g1 => simp [arr, grid, keyP, ofsCarry_zero, key] at hai hti; linarith
      | newlong q =>
        simp [arr, key] at hai
        simp [grid, keyP, ofsCarry_one] at hti
        exact carry_busy_final hL hK hm hai (by linarith) σ
      | g2 =>
        simp [arr, key] at hai
        simp [grid, keyP, ofsCarry_zero] at hti
        have := ff_nonneg (K := K) hL m
        exact carry_busy_final hL hK hm hai (by linarith) σ
      | victim =>
        simp [arr, key] at hai
        simp only [grid, keyP, ofsCarry_one] at hti
        rw [min_eq_right (by omega : m ≤ m + 1)] at hti
        push_cast at hti
        exact carry_busy_final hL hK hm hai hti σ)

/-! #### The victim's `Δ` -/

section Delta

variable (m K) [NeZero K] (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m)

lemma prec_P_iff (i j : UJ m K) : (schedP m K L hL hK hm).prec i j ↔ ordP i < ordP j :=
  Iff.rfl

theorem delta_up :
    Delta (schedP m K L hL hK hm) (schedF m K L hL hK hm) victim = K * (L + ff K L m) := by
  have hWP : (schedP m K L hL hK hm).W victim = L + ff K L m := by
    show grid L (ofsCarry m K L) (keyP victim) - arr m K L victim = _
    simp only [grid, keyP, ofsCarry_one, arr, key]
    rw [min_eq_right (by omega : m ≤ m + 1), min_self]
    push_cast
    ring
  have hWF : (schedF m K L hL hK hm).W victim = 0 := by
    show grid L (ofsFlat m K L) (key victim) - arr m K L victim = _
    simp [grid, key, ofsFlat_zero, arr]
  have hIn : (schedP m K L hL hK hm).In victim = L + ff K L m := by
    unfold Sched.In
    have hset : univ.filter (fun j => victim < j ∧ (schedP m K L hL hK hm).prec j victim)
        = {g1, g2} := by
      ext j
      simp only [Finset.mem_filter, Finset.mem_univ, true_and, Finset.mem_insert,
        Finset.mem_singleton, prec_P_iff, lt_iff, rank_lt_iff, ordP_lt_iff hK]
      cases j <;> simp [key, keyP, idx, lexlt, Prod.ext_iff] <;> omega
    rw [hset, Finset.sum_pair (by simp)]
    rfl
  have hOut : (schedP m K L hL hK hm).Out victim = 0 := by
    unfold Sched.Out
    apply Finset.sum_eq_zero
    intro j hj
    simp only [Finset.mem_filter, Finset.mem_univ, true_and, prec_P_iff, lt_iff, rank_lt_iff,
      ordP_lt_iff hK] at hj
    exfalso
    cases j <;> simp [key, keyP, idx, lexlt, Prod.ext_iff] at hj <;> omega
  unfold Delta
  rw [hWP, hWF, hIn, hOut]
  show ((K + 1 : ℕ) : ℝ) * (L + ff K L m - 0) - (L + ff K L m - 0) = _
  push_cast
  ring

end Delta

end UJ

/-- Theorem "Tightness", upward direction. -/
theorem tight_up (k : ℕ) (hk : 2 ≤ k) (L : ℝ) (hL : 0 < L) (ε : ℝ) (hε : 0 < ε) :
    ∃ (J : Type) (_ : Fintype J) (_ : LinearOrder J) (I : Input J) (P F : Sched I),
      IsFCFS F ∧ I.k = k ∧ I.L = L ∧ ∃ i, 2 * ((k : ℝ) - 1) * L - ε < Delta P F i := by
  obtain ⟨K, rfl⟩ : ∃ K, k = K + 1 := ⟨k - 1, by omega⟩
  have hK : 1 ≤ K := by omega
  haveI : NeZero K := ⟨by omega⟩
  obtain ⟨m, hm, hmε⟩ := ff_tendsto hL hK hε
  refine ⟨UJ m K, inferInstance, inferInstance, UJ.input m K L hL hK hm,
    UJ.schedP m K L hL hK hm, UJ.schedF m K L hL hK hm, UJ.schedF_fcfs m K L hL hK hm,
    rfl, rfl, UJ.victim, ?_⟩
  rw [UJ.delta_up]
  unfold ff
  push_cast
  nlinarith

end Tight


namespace Tight

/-! ### Downward witness -/

/-- Jobs of the downward witness: the mirrored cascade (in each round the short job and
the pieces have lower rank than the long jobs), then a filler of cost `f m`, the victim
and `K` new long jobs. -/
inductive DJ (m K : ℕ) where
  | short0 (r : Fin m)
  | piece (r : Fin m) (q : Fin K)
  | long (r : Fin m) (q : Fin K)
  | filler
  | victim
  | newlong (q : Fin K)
  deriving DecidableEq, Fintype

namespace DJ

variable {m K : ℕ}

/-- FCFS key: here FCFS is the carrying schedule. -/
def key : DJ m K → ℕ × ℕ
  | short0 r => (r, 0)
  | piece r _ => (r, 1)
  | long r _ => (r, 2)
  | filler => (m, 0)
  | victim => (m, 1)
  | newlong _ => (m, 1)

def idx : DJ m K → ℕ
  | short0 _ => 0
  | piece _ q => q
  | long _ q => q
  | filler => 0
  | victim => 0
  | newlong q => q + 1

lemma key_snd_lt (j : DJ m K) : (key j).2 < K + 3 := by
  cases j <;> simp [key] <;> omega

lemma idx_lt (j : DJ m K) : idx j < K + 3 := by
  cases j <;> simp [idx] <;> omega

def rank (j : DJ m K) : ℕ := enc2 (K + 3) (key j) (idx j)

lemma rank_lt_iff (i j : DJ m K) :
    rank i < rank j ↔ lexlt (key i) (key j) ∨ (key i = key j ∧ idx i < idx j) :=
  enc2_lt_iff (key_snd_lt i) (key_snd_lt j) (idx_lt i) (idx_lt j)

lemma rank_inj : Function.Injective (@rank m K) := by
  intro a b h
  obtain ⟨h1, h2⟩ := enc2_inj (key_snd_lt a) (key_snd_lt b) (idx_lt a) (idx_lt b) h
  cases a <;> cases b <;> simp [key, idx, Prod.ext_iff, Fin.ext_iff] at h1 h2 ⊢ <;> omega

instance : LinearOrder (DJ m K) := LinearOrder.lift' rank rank_inj

lemma lt_iff (i j : DJ m K) : i < j ↔ rank i < rank j := Iff.rfl

variable (m K) in
def arr (L : ℝ) (j : DJ m K) : ℝ := ((min (key j).1 m : ℕ) : ℝ) * L

variable (m K) in
def cost (L : ℝ) : DJ m K → ℝ
  | short0 r => ff K L (r + 1)
  | piece r _ => dd K L r
  | long _ _ => L
  | filler => ff K L m
  | victim => L
  | newlong _ => L

lemma min_fin (r : Fin m) : min (r : ℕ) m = r := min_eq_left r.isLt.le

def input (m K : ℕ) (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m) : Input (DJ m K) where
  k := K + 1
  L := L
  a := arr m K L
  C := cost m K L
  hk := by omega
  hL := hL
  ha_nonneg j := by unfold arr; positivity
  ha_mono := by
    intro i j hij
    have h1 : (key i).1 ≤ (key j).1 := by
      have : ¬ rank j < rank i := not_lt.mpr hij
      rw [rank_lt_iff] at this
      unfold lexlt at this
      omega
    have : ((min (key i).1 m : ℕ) : ℝ) ≤ (min (key j).1 m : ℕ) := by
      exact_mod_cast min_le_min_right m h1
    exact mul_le_mul_of_nonneg_right this hL.le
  hC_pos j := by
    cases j with
    | short0 r => exact ff_succ_pos hL hK r
    | piece r => exact dd_pos hL hK r
    | long => exact hL
    | filler =>
      obtain ⟨m', rfl⟩ : ∃ m', m = m' + 1 := ⟨m - 1, by omega⟩
      exact ff_succ_pos hL hK m'
    | victim => exact hL
    | newlong => exact hL
  hC_le j := by
    cases j with
    | short0 r => exact ff_le hL hK _
    | piece r =>
      show dd K L r ≤ L
      unfold dd
      linarith [ff_nonneg (K := K) hL r, ff_le (K := K) hL hK (r + 1)]
    | long => exact le_rfl
    | filler => exact ff_le hL hK _
    | victim => exact le_rfl
    | newlong => exact le_rfl

/-! #### The FCFS schedule (carrying) -/

def srvF [NeZero K] : DJ m K → Fin (K + 1)
  | short0 _ => Fin.last K
  | piece _ q => q.castSucc
  | long _ q => q.castSucc
  | filler => Fin.last K
  | victim => Fin.last K
  | newlong q => q.castSucc

def hiF : DJ m K → ℕ × ℕ
  | short0 r => (r, 2)
  | piece r _ => (r, 2)
  | long r _ => (r + 1, 1)
  | filler => (m, 1)
  | victim => (m + 1, 1)
  | newlong _ => (m + 1, 1)

lemma pairF [NeZero K] (i j : DJ m K) (hij : i ≠ j) (hs : srvF i = srvF j) :
    lexle (hiF i) (key j) ∨ lexle (hiF j) (key i) := by
  have hK0 : K ≠ 0 := NeZero.ne K
  cases i <;> cases j <;> simp only [srvF, hiF, key, lexle, Fin.ext_iff, Fin.val_last,
    Fin.val_castSucc, ne_eq, reduceCtorEq, not_false_eq_true, not_true_eq_false, eq_self_iff_true,
    DJ.long.injEq, DJ.short0.injEq, DJ.piece.injEq, DJ.newlong.injEq] at hij hs ⊢ <;>
    (try simp only [true_and, and_true, true_or, or_true, le_refl] at hij hs ⊢) <;> omega

section F

variable {L : ℝ} (hL : 0 < L) (hK : 1 ≤ K)
include hL hK

lemma carry_busy [NeZero K] (r : Fin m) {t : ℝ} (h1 : (r : ℝ) * L ≤ t)
    (h2 : t < r * L + ff K L (r + 1)) (σ : Fin (K + 1)) :
    ∃ j : DJ m K, srvF j = σ ∧ grid L (ofsCarry m K L) (key j) ≤ t ∧
      t < grid L (ofsCarry m K L) (key j) + cost m K L j := by
  induction σ using Fin.lastCases with
  | last =>
    exact ⟨short0 r, rfl, by simp [grid, key, ofsCarry_zero]; linarith,
      by simp [grid, key, ofsCarry_zero, cost]; linarith⟩
  | cast q =>
    by_cases h3 : t < r * L + ff K L r
    · obtain ⟨r', hr'⟩ : ∃ r' : ℕ, (r : ℕ) = r' + 1 := by
        rcases Nat.eq_zero_or_pos (r : ℕ) with h0 | h0
        · rw [h0, ff_zero] at h3
          simp [h0] at h1 h3
          linarith
        · exact ⟨(r : ℕ) - 1, by omega⟩
      have hfL := ff_le (K := K) hL hK (r' + 1)
      refine ⟨long ⟨r', by omega⟩ q, rfl, ?_, ?_⟩
      · simp only [grid, key, ofsCarry_two]
        rw [hr'] at h1
        push_cast at h1
        linarith
      · simp only [grid, key, ofsCarry_two, cost]
        rw [hr'] at h3
        push_cast at h3
        linarith
    · push Not at h3
      refine ⟨piece r q, rfl, ?_, ?_⟩
      · simp only [grid, key, ofsCarry_one, min_fin]
        exact h3
      · simp only [grid, key, ofsCarry_one, min_fin, cost, dd]
        linarith

lemma carry_busy_final [NeZero K] (hm : 1 ≤ m) {t : ℝ} (h1 : (m : ℝ) * L ≤ t)
    (h2 : t < m * L + ff K L m) (σ : Fin (K + 1)) :
    ∃ j : DJ m K, srvF j = σ ∧ grid L (ofsCarry m K L) (key j) ≤ t ∧
      t < grid L (ofsCarry m K L) (key j) + cost m K L j := by
  induction σ using Fin.lastCases with
  | last =>
    exact ⟨filler, rfl, by simp [grid, key, ofsCarry_zero]; linarith,
      by simp [grid, key, ofsCarry_zero, cost]; linarith⟩
  | cast q =>
    obtain ⟨m', rfl⟩ : ∃ m' : ℕ, m = m' + 1 := ⟨m - 1, by omega⟩
    have hfL := ff_le (K := K) hL hK (m' + 1)
    refine ⟨long ⟨m', by omega⟩ q, rfl, ?_, ?_⟩
    · simp only [grid, key, ofsCarry_two]
      push_cast at h1 ⊢
      linarith
    · simp only [grid, key, ofsCarry_two, cost]
      push_cast at h2 ⊢
      linarith

end F

def schedF (m K : ℕ) [NeZero K] (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m) :
    Sched (input m K L hL hK hm) :=
  mkSched (input m K L hL hK hm) L (ofsCarry m K L) (good_carry hL hK) key hiF srvF rank
    rank_inj
    (fun i j h => (rank_lt_iff j i).mpr (Or.inl h))
    (by
      intro j
      show arr m K L j ≤ grid L (ofsCarry m K L) (key j)
      unfold arr grid
      have h1 : ((min (key j).1 m : ℕ) : ℝ) ≤ (key j).1 := by exact_mod_cast min_le_left _ _
      have := (good_carry (m := m) hL hK).nonneg (key j).1 (key j).2
      nlinarith)
    (by
      intro j
      show grid L (ofsCarry m K L) (key j) + cost m K L j ≤ grid L (ofsCarry m K L) (hiF j)
      have hfL := ff_le (K := K) hL hK m
      cases j with
      | short0 r => simp [grid, key, hiF, ofsCarry_zero, ofsCarry_two, cost]
      | piece r q => simp [grid, key, hiF, ofsCarry_one, ofsCarry_two, min_fin, cost, dd]
      | long r q =>
        simp only [grid, key, hiF, ofsCarry_one, ofsCarry_two, cost]
        rw [min_eq_left (by omega : (r : ℕ) + 1 ≤ m)]
        push_cast
        linarith
      | filler => simp [grid, key, hiF, ofsCarry_zero, ofsCarry_one, cost]
      | victim =>
        simp only [grid, key, hiF, ofsCarry_one, cost]
        rw [min_eq_right (by omega : m ≤ m + 1), min_self]
        push_cast
        linarith
      | newlong q =>
        simp only [grid, key, hiF, ofsCarry_one, cost]
        rw [min_eq_right (by omega : m ≤ m + 1), min_self]
        push_cast
        linarith)
    (fun i j hij hs => pairF i j hij hs)
    (by
      rintro t ⟨i, hai, hti⟩ σ
      change arr m K L i ≤ t at hai
      cases i with
      | short0 r => simp [arr, grid, key, ofsCarry_zero] at hai hti; linarith
      | piece r q =>
        simp only [arr, key, min_fin] at hai
        simp only [grid, key, ofsCarry_one, min_fin] at hti
        have := ff_mono (K := K) hL (Nat.le_succ (r : ℕ))
        exact carry_busy hL hK r hai (by linarith) σ
      | long r q =>
        simp only [arr, key, min_fin] at hai
        simp only [grid, key, ofsCarry_two] at hti
        exact carry_busy hL hK r hai hti σ
      | filler => simp [arr, grid, key, ofsCarry_zero] at hai hti; linarith
      | victim =>
        simp [arr, key] at hai
        simp [grid, key, ofsCarry_one] at hti
        exact carry_busy_final hL hK hm hai hti σ
      | newlong q =>
        simp [arr, key] at hai
        simp [grid, key, ofsCarry_one] at hti
        exact carry_busy_final hL hK hm hai hti σ)

lemma schedF_fcfs (m K : ℕ) [NeZero K] (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m) :
    IsFCFS (schedF m K L hL hK hm) := fun _ _ => Iff.rfl

/-! #### The base policy `P` (flat, long jobs first) -/

def keyP : DJ m K → ℕ × ℕ
  | long r _ => (r, 0)
  | short0 r => (r, 0)
  | piece r q => (r, q + 1)
  | newlong _ => (m, 0)
  | victim => (m, 1)
  | filler => (m + 1, 0)

def hiP : DJ m K → ℕ × ℕ
  | long r _ => (r + 1, 0)
  | short0 r => (r, 1)
  | piece r q => (r, q + 2)
  | newlong _ => (m + 1, 0)
  | victim => (m + 1, 0)
  | filler => (m + 2, 0)

def srvP [NeZero K] : DJ m K → Fin (K + 1)
  | long _ q => q.castSucc
  | short0 _ => Fin.last K
  | piece _ _ => Fin.last K
  | newlong q => q.castSucc
  | victim => Fin.last K
  | filler => Fin.last K

lemma keyP_snd_lt (j : DJ m K) : (keyP j).2 < K + 3 := by
  cases j <;> simp [keyP] <;> omega

variable (m K) in
def big : ℕ := enc2 (K + 3) (m + 2, 0) 0

lemma rank_lt_big (j : DJ m K) : rank j < big m K := by
  unfold big rank
  rw [enc2_lt_iff (key_snd_lt j) (by simp) (idx_lt j) (by omega)]
  left
  cases j <;> simp [key, lexlt] <;> omega

def ordP (j : DJ m K) : ℕ := enc (big m K) (enc (K + 3) (keyP j), rank j)

lemma ordP_lt_iff (i j : DJ m K) :
    ordP i < ordP j ↔ lexlt (keyP i) (keyP j) ∨ (keyP i = keyP j ∧ rank i < rank j) := by
  unfold ordP enc
  rw [mul_add_lt_iff (rank_lt_big i) (rank_lt_big j)]
  change enc (K + 3) (keyP i) < enc (K + 3) (keyP j) ∨ _ ↔ _
  rw [enc_lt_iff (keyP_snd_lt i) (keyP_snd_lt j)]
  constructor
  · rintro (h | ⟨h1, h2⟩)
    · exact Or.inl h
    · exact Or.inr ⟨enc_inj (keyP_snd_lt i) (keyP_snd_lt j) h1, h2⟩
  · rintro (h | ⟨h1, h2⟩)
    · exact Or.inl h
    · exact Or.inr ⟨by rw [h1], h2⟩

lemma ordP_inj : Function.Injective (@ordP m K) := by
  intro a b h
  exact rank_inj (mul_add_inj (rank_lt_big a) (rank_lt_big b) h).2

lemma pairP [NeZero K] (i j : DJ m K) (hij : i ≠ j) (hs : srvP i = srvP j) :
    lexle (hiP i) (keyP j) ∨ lexle (hiP j) (keyP i) := by
  have hK0 : K ≠ 0 := NeZero.ne K
  cases i <;> cases j <;> simp only [srvP, hiP, keyP, lexle, Fin.ext_iff, Fin.val_last,
    Fin.val_castSucc, ne_eq, reduceCtorEq, not_false_eq_true, not_true_eq_false, eq_self_iff_true,
    DJ.long.injEq, DJ.short0.injEq, DJ.piece.injEq, DJ.newlong.injEq] at hij hs ⊢ <;>
    (try simp only [true_and, and_true, true_or, or_true, le_refl] at hij hs ⊢) <;> omega

section P

variable {L : ℝ} (hL : 0 < L) (hK : 1 ≤ K)
include hL hK

lemma sP_piece (r : Fin m) (q : Fin K) :
    grid L (ofsFlat m K L) (keyP (piece r q)) = r * L + ff K L (r + 1) + q * dd K L r := by
  simp only [grid, keyP]
  rw [ofsFlat_piece hL hK r.isLt q.isLt.le]
  ring

lemma flat_busy [NeZero K] (r : Fin m) {t : ℝ} (h1 : (r : ℝ) * L ≤ t) (h2 : t < r * L + L)
    (σ : Fin (K + 1)) : ∃ j : DJ m K, srvP j = σ ∧ grid L (ofsFlat m K L) (keyP j) ≤ t ∧
      t < grid L (ofsFlat m K L) (keyP j) + cost m K L j := by
  induction σ using Fin.lastCases with
  | last =>
    by_cases h3 : t < r * L + ff K L (r + 1)
    · exact ⟨short0 r, rfl, by simp [grid, keyP, ofsFlat_zero]; linarith,
        by simp [grid, keyP, ofsFlat_zero, cost]; linarith⟩
    · push Not at h3
      have hfill := ff_fill (K := K) (L := L) r
      obtain ⟨q, hq, hq1, hq2⟩ := find_piece (K := K) (dd_pos hL hK r) h3 (by linarith)
      refine ⟨piece r ⟨q, hq⟩, rfl, ?_, ?_⟩
      · rw [sP_piece hL hK]
        exact hq1
      · rw [sP_piece hL hK]
        exact hq2
  | cast q =>
    exact ⟨long r q, rfl, by simp [grid, keyP, ofsFlat_zero]; linarith,
      by simp [grid, keyP, ofsFlat_zero, cost]; linarith⟩

lemma flat_busy_final [NeZero K] {t : ℝ} (h1 : (m : ℝ) * L ≤ t) (h2 : t < m * L + L)
    (σ : Fin (K + 1)) : ∃ j : DJ m K, srvP j = σ ∧ grid L (ofsFlat m K L) (keyP j) ≤ t ∧
      t < grid L (ofsFlat m K L) (keyP j) + cost m K L j := by
  induction σ using Fin.lastCases with
  | last =>
    exact ⟨victim, rfl, by simp [grid, keyP, ofsFlat_late (le_refl m)]; linarith,
      by simp [grid, keyP, ofsFlat_late (le_refl m), cost]; linarith⟩
  | cast q =>
    exact ⟨newlong q, rfl, by simp [grid, keyP, ofsFlat_zero]; linarith,
      by simp [grid, keyP, ofsFlat_zero, cost]; linarith⟩

end P

def schedP (m K : ℕ) [NeZero K] (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m) :
    Sched (input m K L hL hK hm) :=
  mkSched (input m K L hL hK hm) L (ofsFlat m K L) (good_flat hL hK) keyP hiP srvP ordP
    ordP_inj
    (fun i j h => (ordP_lt_iff j i).mpr (Or.inl h))
    (by
      intro j
      show arr m K L j ≤ grid L (ofsFlat m K L) (keyP j)
      unfold arr grid
      have h0 : min (key j).1 m ≤ (keyP j).1 := by
        cases j <;> simp [key, keyP] <;> omega
      have h1 : ((min (key j).1 m : ℕ) : ℝ) ≤ (keyP j).1 := by exact_mod_cast h0
      have := (good_flat (m := m) hL hK).nonneg (keyP j).1 (keyP j).2
      nlinarith)
    (by
      intro j
      show grid L (ofsFlat m K L) (keyP j) + cost m K L j ≤ grid L (ofsFlat m K L) (hiP j)
      cases j with
      | long r q => simp [grid, keyP, hiP, ofsFlat_zero, cost]; linarith
      | short0 r =>
        simp only [grid, keyP, hiP, ofsFlat_zero, cost]
        rw [show (1 : ℕ) = 0 + 1 from rfl, ofsFlat_piece hL hK r.isLt (Nat.zero_le _)]
        simp
      | piece r q =>
        simp only [grid, keyP, hiP, cost]
        rw [ofsFlat_piece hL hK r.isLt q.isLt.le,
          show (q : ℕ) + 2 = ((q : ℕ) + 1) + 1 by ring,
          ofsFlat_piece hL hK r.isLt (by omega)]
        push_cast
        ring_nf
        rfl
      | newlong q => simp [grid, keyP, hiP, ofsFlat_zero, cost]; linarith
      | victim =>
        simp [grid, keyP, hiP, ofsFlat_zero, ofsFlat_late (le_refl m), cost]; linarith
      | filler =>
        simp [grid, keyP, hiP, ofsFlat_zero, cost]
        linarith [ff_le (K := K) hL hK m])
    (fun i j hij hs => pairP i j hij hs)
    (by
      rintro t ⟨i, hai, hti⟩ σ
      change arr m K L i ≤ t at hai
      cases i with
      | long r q => simp [arr, grid, keyP, key, ofsFlat_zero, min_fin] at hai hti; linarith
      | short0 r => simp [arr, grid, keyP, key, ofsFlat_zero, min_fin] at hai hti; linarith
      | piece r q =>
        simp only [arr, key, min_fin] at hai
        rw [sP_piece hL hK] at hti
        have := flat_piece_le hL hK r q q.isLt.le
        have := dd_pos hL hK r
        exact flat_busy hL hK r hai (by linarith) σ
      | newlong q => simp [arr, grid, keyP, key, ofsFlat_zero] at hai hti; linarith
      | victim =>
        simp [arr, grid, keyP, key, ofsFlat_late (le_refl m)] at hai hti; linarith
      | filler =>
        simp [arr, grid, keyP, key, ofsFlat_zero] at hai hti
        exact flat_busy_final hL hK hai (by push_cast at hti; linarith) σ)

/-! #### The victim's `Δ` -/

section Delta

variable (m K) [NeZero K] (L : ℝ) (hL : 0 < L) (hK : 1 ≤ K) (hm : 1 ≤ m)

lemma prec_P_iff (i j : DJ m K) : (schedP m K L hL hK hm).prec i j ↔ ordP i < ordP j :=
  Iff.rfl

theorem delta_down :
    Delta (schedP m K L hL hK hm) (schedF m K L hL hK hm) victim =
      -(K * L) - K * ff K L m := by
  have hWP : (schedP m K L hL hK hm).W victim = 0 := by
    show grid L (ofsFlat m K L) (keyP victim) - arr m K L victim = _
    simp [grid, keyP, ofsFlat_late (le_refl m), arr, key]
  have hWF : (schedF m K L hL hK hm).W victim = ff K L m := by
    show grid L (ofsCarry m K L) (key victim) - arr m K L victim = _
    simp [grid, key, ofsCarry_one, arr]
  have hIn : (schedP m K L hL hK hm).In victim = K * L := by
    unfold Sched.In
    have hset : univ.filter (fun j => victim < j ∧ (schedP m K L hL hK hm).prec j victim)
        = univ.map ⟨newlong, fun a b h => by cases h; rfl⟩ := by
      ext j
      simp only [Finset.mem_filter, Finset.mem_univ, true_and, Finset.mem_map,
        prec_P_iff, lt_iff, rank_lt_iff, ordP_lt_iff]
      cases j <;> simp [key, keyP, idx, lexlt, Prod.ext_iff] <;> first | omega | exact ⟨_, rfl⟩
    rw [hset, Finset.sum_map]
    show ∑ _q : Fin K, L = _
    simp
  have hOut : (schedP m K L hL hK hm).Out victim = ff K L m := by
    unfold Sched.Out
    have hset : univ.filter (fun j => j < victim ∧ (schedP m K L hL hK hm).prec victim j)
        = {filler} := by
      ext j
      simp only [Finset.mem_filter, Finset.mem_univ, true_and, Finset.mem_singleton,
        prec_P_iff, lt_iff, rank_lt_iff, ordP_lt_iff]
      cases j <;> simp [key, keyP, idx, lexlt, Prod.ext_iff] <;> omega
    rw [hset, Finset.sum_singleton]
    rfl
  unfold Delta
  rw [hWP, hWF, hIn, hOut]
  show ((K + 1 : ℕ) : ℝ) * (0 - ff K L m) - (K * L - ff K L m) = _
  push_cast
  ring

end Delta

end DJ

/-- Theorem "Tightness", downward direction. -/
theorem tight_down (k : ℕ) (hk : 2 ≤ k) (L : ℝ) (hL : 0 < L) (ε : ℝ) (hε : 0 < ε) :
    ∃ (J : Type) (_ : Fintype J) (_ : LinearOrder J) (I : Input J) (P F : Sched I),
      IsFCFS F ∧ I.k = k ∧ I.L = L ∧ ∃ i, Delta P F i < -(2 * ((k : ℝ) - 1) * L) + ε := by
  obtain ⟨K, rfl⟩ : ∃ K, k = K + 1 := ⟨k - 1, by omega⟩
  have hK : 1 ≤ K := by omega
  have : NeZero K := ⟨by omega⟩
  obtain ⟨m, hm, hmε⟩ := ff_tendsto hL hK hε
  refine ⟨DJ m K, inferInstance, inferInstance, DJ.input m K L hL hK hm,
    DJ.schedP m K L hL hK hm, DJ.schedF m K L hL hK hm, DJ.schedF_fcfs m K L hL hK hm,
    rfl, rfl, DJ.victim, ?_⟩
  rw [DJ.delta_down]
  unfold ff
  push_cast
  nlinarith

end Tight

/-- Theorem "Tightness" (06_theory.tex:189), as stated: for every `k ≥ 2`, `L > 0` and
`ε > 0` there are witnesses with `Δ_i > 2(k-1)L - ε` and witnesses with
`Δ_i < -2(k-1)L + ε`; with `identity_bound_strict` the supremum `2(k-1)L` of `|Δ_i|` is
never attained. -/
theorem tightness (k : ℕ) (hk : 2 ≤ k) (L : ℝ) (hL : 0 < L) (ε : ℝ) (hε : 0 < ε) :
    (∃ (J : Type) (_ : Fintype J) (_ : LinearOrder J) (I : Input J) (P F : Sched I),
      IsFCFS F ∧ I.k = k ∧ I.L = L ∧ ∃ i, 2 * ((k : ℝ) - 1) * L - ε < Delta P F i) ∧
    (∃ (J : Type) (_ : Fintype J) (_ : LinearOrder J) (I : Input J) (P F : Sched I),
      IsFCFS F ∧ I.k = k ∧ I.L = L ∧ ∃ i, Delta P F i < -(2 * ((k : ℝ) - 1) * L) + ε) :=
  ⟨Tight.tight_up k hk L hL ε hε, Tight.tight_down k hk L hL ε hε⟩

/-- Lemma "Workload comparison", the constant `(k-1)L` is approached (k ≥ 2): obtained
from the upward witness through the identity, since `β^P ≥ 0` and `β^FCFS ≤ (k-1)L`. -/
theorem workload_comparison_approached (k : ℕ) (hk : 2 ≤ k) (L : ℝ) (hL : 0 < L)
    (ε : ℝ) (hε : 0 < ε) :
    ∃ (J : Type) (_ : Fintype J) (_ : LinearOrder J) (I : Input J) (P F : Sched I),
      I.k = k ∧ I.L = L ∧ ∃ t, ((k : ℝ) - 1) * L - ε < P.U t - F.U t := by
  obtain ⟨J, _, _, I, P, F, hF, hk', hL', i, hi⟩ := Tight.tight_up k hk L hL ε hε
  refine ⟨J, inferInstance, inferInstance, I, P, F, hk', hL', I.a i, ?_⟩
  rw [identity P F hF i, R_sub_R] at hi
  have h1 := P.beta_nonneg i
  have h2 := F.beta_le i
  rw [hk', hL'] at h2
  linarith

end Overtake

/-! ## Axiom check -/

#print axioms Overtake.workload_comparison
#print axioms Overtake.workload_comparison_k1
#print axioms Overtake.workload_comparison_strict
#print axioms Overtake.fcfs_unique
#print axioms Overtake.Sched.busy
#print axioms Overtake.identity
#print axioms Overtake.identity_bound
#print axioms Overtake.identity_bound'
#print axioms Overtake.identity_k1
#print axioms Overtake.identity_bound_strict
#print axioms Overtake.sufficient
#print axioms Overtake.sufficient_In
#print axioms Overtake.outbound
#print axioms Overtake.necessary
#print axioms Overtake.Tight.tight_up
#print axioms Overtake.Tight.tight_down
#print axioms Overtake.tightness
#print axioms Overtake.workload_comparison_approached

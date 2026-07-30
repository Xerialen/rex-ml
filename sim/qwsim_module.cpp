// pybind11 bindings for libqwsim. numpy in/out, GIL released around the
// batched C entry points (they are GIL-free by construction).
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <stdexcept>
#include <cstring>
#include "csrc/qwsim_api.h"

namespace py = pybind11;

template <typename T>
static const T *req_in (const py::array_t<T, py::array::c_style | py::array::forcecast> &a,
                        ssize_t n, ssize_t inner, const char *name)
{
	if (inner == 1) {
		if (a.ndim() != 1 || a.shape(0) != n)
			throw std::runtime_error(std::string(name) + ": expected shape (" + std::to_string(n) + ",)");
	} else {
		if (a.ndim() != 2 || a.shape(0) != n || a.shape(1) != inner)
			throw std::runtime_error(std::string(name) + ": expected shape (" + std::to_string(n) + "," + std::to_string(inner) + ")");
	}
	return a.data();
}

static qwsim_movevars_t movevars_from_dict (py::dict d)
{
	qwsim_movevars_t mv;
	qwsim_get_movevars(&mv);
	for (auto item : d) {
		std::string k = py::cast<std::string>(item.first);
		double v = py::cast<double>(item.second);
		if      (k == "gravity")            mv.gravity = v;
		else if (k == "stopspeed")          mv.stopspeed = v;
		else if (k == "maxspeed")           mv.maxspeed = v;
		else if (k == "spectatormaxspeed")  mv.spectatormaxspeed = v;
		else if (k == "accelerate")         mv.accelerate = v;
		else if (k == "airaccelerate")      mv.airaccelerate = v;
		else if (k == "wateraccelerate")    mv.wateraccelerate = v;
		else if (k == "friction")           mv.friction = v;
		else if (k == "waterfriction")      mv.waterfriction = v;
		else if (k == "entgravity")         mv.entgravity = v;
		else if (k == "bunnyspeedcap")      mv.bunnyspeedcap = v;
		else if (k == "ktjump")             mv.ktjump = v;
		else if (k == "slidefix")           mv.slidefix = (int)v;
		else if (k == "airstep")            mv.airstep = (int)v;
		else if (k == "pground")            mv.pground = (int)v;
		else if (k == "rampjump")           mv.rampjump = (int)v;
		else throw std::runtime_error("unknown movevar: " + k);
	}
	return mv;
}

static py::dict movevars_to_dict (const qwsim_movevars_t &mv)
{
	py::dict d;
	d["gravity"] = mv.gravity; d["stopspeed"] = mv.stopspeed;
	d["maxspeed"] = mv.maxspeed; d["spectatormaxspeed"] = mv.spectatormaxspeed;
	d["accelerate"] = mv.accelerate; d["airaccelerate"] = mv.airaccelerate;
	d["wateraccelerate"] = mv.wateraccelerate;
	d["friction"] = mv.friction; d["waterfriction"] = mv.waterfriction;
	d["entgravity"] = mv.entgravity; d["bunnyspeedcap"] = mv.bunnyspeedcap;
	d["ktjump"] = mv.ktjump; d["slidefix"] = mv.slidefix;
	d["airstep"] = mv.airstep; d["pground"] = mv.pground;
	d["rampjump"] = mv.rampjump;
	return d;
}

PYBIND11_MODULE(qwsim, m)
{
	m.doc() = "Batched, GIL-free, bit-exact QuakeWorld player physics (mvdsv pmove extraction)";

	m.def("load_bsp", [](const std::string &path) {
		char err[512] = {0};
		int rc;
		{
			py::gil_scoped_release rel;
			rc = qwsim_load_bsp(path.c_str(), err, sizeof(err));
		}
		if (rc != 0)
			throw std::runtime_error("load_bsp failed: " + std::string(err));
		return qwsim_map_checksum2();
	}, py::arg("path"),
	"Load a BSP world (returns checksum2). Replaces any previously loaded map.");

	m.def("unload_bsp", []() { qwsim_unload_bsp(); });
	m.def("map_loaded", []() { return (bool)qwsim_map_loaded(); });

	m.def("default_movevars", []() {
		qwsim_movevars_t mv; qwsim_get_default_movevars(&mv);
		return movevars_to_dict(mv);
	});
	m.def("set_movevars", [](py::dict d) {
		qwsim_movevars_t mv = movevars_from_dict(d);
		qwsim_set_movevars(&mv);
	}, py::arg("movevars"));
	m.def("get_movevars", []() {
		qwsim_movevars_t mv; qwsim_get_movevars(&mv);
		return movevars_to_dict(mv);
	});

	m.def("alloc_slots", [](int n) { return qwsim_alloc_slots(n); }, py::arg("n"));
	m.def("num_slots", []() { return qwsim_num_slots(); });
	m.def("set_num_threads", [](int n) { qwsim_set_num_threads(n); }, py::arg("n"));
	m.def("get_num_threads", []() { return qwsim_get_num_threads(); });

	m.def("reset",
	      [](py::array_t<int32_t, py::array::c_style | py::array::forcecast> slot_ids,
	         py::array_t<float, py::array::c_style | py::array::forcecast> pos,
	         py::array_t<float, py::array::c_style | py::array::forcecast> vel,
	         py::object angles,
	         py::object onground, py::object jump_held, py::object waterjumptime) {
		ssize_t n = slot_ids.shape(0);
		const int32_t *ids = req_in(slot_ids, n, 1, "slot_ids");
		const float *p = req_in(pos, n, 3, "pos");
		const float *v = req_in(vel, n, 3, "vel");

		py::array_t<float, py::array::c_style | py::array::forcecast> ang_a;
		const float *ang = nullptr;
		if (!angles.is_none()) {
			ang_a = py::cast<py::array_t<float, py::array::c_style | py::array::forcecast>>(angles);
			ang = req_in(ang_a, n, 3, "angles");
		}
		py::array_t<uint8_t, py::array::c_style | py::array::forcecast> og_a, jh_a;
		const uint8_t *og = nullptr, *jh = nullptr;
		if (!onground.is_none()) {
			og_a = py::cast<py::array_t<uint8_t, py::array::c_style | py::array::forcecast>>(onground);
			og = req_in(og_a, n, 1, "onground");
		}
		if (!jump_held.is_none()) {
			jh_a = py::cast<py::array_t<uint8_t, py::array::c_style | py::array::forcecast>>(jump_held);
			jh = req_in(jh_a, n, 1, "jump_held");
		}
		py::array_t<float, py::array::c_style | py::array::forcecast> wj_a;
		const float *wj = nullptr;
		if (!waterjumptime.is_none()) {
			wj_a = py::cast<py::array_t<float, py::array::c_style | py::array::forcecast>>(waterjumptime);
			wj = req_in(wj_a, n, 1, "waterjumptime");
		}
		py::gil_scoped_release rel;
		qwsim_reset_slots((int)n, ids, p, v, ang, og, jh, wj);
	}, py::arg("slot_ids"), py::arg("pos"), py::arg("vel"),
	   py::arg("angles") = py::none(),
	   py::arg("onground") = py::none(), py::arg("jump_held") = py::none(),
	   py::arg("waterjumptime") = py::none());

	m.def("step_batch",
	      [](py::array_t<int32_t, py::array::c_style | py::array::forcecast> slot_ids,
	         py::array_t<float,   py::array::c_style | py::array::forcecast> angles,
	         py::array_t<int16_t, py::array::c_style | py::array::forcecast> forwardmove,
	         py::array_t<int16_t, py::array::c_style | py::array::forcecast> sidemove,
	         py::array_t<int16_t, py::array::c_style | py::array::forcecast> upmove,
	         py::array_t<uint8_t, py::array::c_style | py::array::forcecast> buttons,
	         py::array_t<uint8_t, py::array::c_style | py::array::forcecast> msec) {
		ssize_t n = slot_ids.shape(0);
		const int32_t *ids = req_in(slot_ids, n, 1, "slot_ids");
		const float *ang = req_in(angles, n, 3, "angles");
		const int16_t *fm = req_in(forwardmove, n, 1, "forwardmove");
		const int16_t *sm = req_in(sidemove, n, 1, "sidemove");
		const int16_t *um = req_in(upmove, n, 1, "upmove");
		const uint8_t *bt = req_in(buttons, n, 1, "buttons");
		const uint8_t *ms = req_in(msec, n, 1, "msec");

		auto pos = py::array_t<float>({n, (ssize_t)3});
		auto vel = py::array_t<float>({n, (ssize_t)3});
		auto onground = py::array_t<uint8_t>(n);
		auto waterlevel = py::array_t<uint8_t>(n);
		auto jump_held = py::array_t<uint8_t>(n);
		auto blocked = py::array_t<int32_t>(n);
		float *pp = pos.mutable_data(), *pv = vel.mutable_data();
		uint8_t *pog = onground.mutable_data(), *pwl = waterlevel.mutable_data();
		uint8_t *pjh = jump_held.mutable_data();
		int32_t *pbl = blocked.mutable_data();
		{
			py::gil_scoped_release rel;
			qwsim_step_batch((int)n, ids, ang, fm, sm, um, bt, ms,
			                 pp, pv, pog, pwl, pjh, pbl);
		}
		return py::make_tuple(pos, vel, onground, waterlevel, jump_held, blocked);
	}, py::arg("slot_ids"), py::arg("angles"), py::arg("forwardmove"),
	   py::arg("sidemove"), py::arg("upmove"), py::arg("buttons"), py::arg("msec"),
	"One server tick for each listed slot. Returns (pos[N,3] f32, vel[N,3] f32, "
	"onground[N] u8, waterlevel[N] u8, jump_held[N] u8, blocked[N] i32).");

	m.def("get_state",
	      [](py::array_t<int32_t, py::array::c_style | py::array::forcecast> slot_ids) {
		ssize_t n = slot_ids.shape(0);
		const int32_t *ids = req_in(slot_ids, n, 1, "slot_ids");
		auto pos = py::array_t<float>({n, (ssize_t)3});
		auto vel = py::array_t<float>({n, (ssize_t)3});
		auto ang = py::array_t<float>({n, (ssize_t)3});
		auto onground = py::array_t<uint8_t>(n);
		auto waterlevel = py::array_t<uint8_t>(n);
		auto jump_held = py::array_t<uint8_t>(n);
		auto wjt = py::array_t<float>(n);
		{
			py::gil_scoped_release rel;
			qwsim_get_state((int)n, ids, pos.mutable_data(), vel.mutable_data(),
			                ang.mutable_data(), onground.mutable_data(),
			                waterlevel.mutable_data(), jump_held.mutable_data(),
			                wjt.mutable_data());
		}
		return py::make_tuple(pos, vel, ang, onground, waterlevel, jump_held, wjt);
	}, py::arg("slot_ids"),
	"Pure read of slot state: (pos, vel, angles, onground, waterlevel, jump_held, waterjumptime).");

	m.def("trace_rays",
	      [](py::array_t<float, py::array::c_style | py::array::forcecast> origins,
	         py::array_t<float, py::array::c_style | py::array::forcecast> dirs,
	         float max_dist) {
		ssize_t n = origins.shape(0);
		const float *po = req_in(origins, n, 3, "origins");
		const float *pd = req_in(dirs, n, 3, "dirs");
		auto fractions = py::array_t<float>(n);
		auto normals = py::array_t<float>({n, (ssize_t)3});
		auto startsolid = py::array_t<uint8_t>(n);
		{
			py::gil_scoped_release rel;
			qwsim_trace_rays((int)n, po, pd, max_dist,
			                 fractions.mutable_data(), normals.mutable_data(),
			                 startsolid.mutable_data());
		}
		return py::make_tuple(fractions, normals, startsolid);
	}, py::arg("origins"), py::arg("dirs"), py::arg("max_dist"),
	"Batched perception rays vs world hull 0. Returns (fractions[M] f32, "
	"normals[M,3] f32, startsolid[M] u8).");

	m.def("point_contents",
	      [](py::array_t<float, py::array::c_style | py::array::forcecast> points) {
		ssize_t n = points.shape(0);
		const float *pp = req_in(points, n, 3, "points");
		auto contents = py::array_t<int32_t>(n);
		{
			py::gil_scoped_release rel;
			qwsim_point_contents((int)n, pp, contents.mutable_data());
		}
		return contents;
	}, py::arg("points"));
}
